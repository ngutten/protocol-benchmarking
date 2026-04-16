"""Stage 3 training tests: chat, self-descriptions, persistent graffiti,
and NPCs are playable as intended.

These exercise the golden paths for the new Stage 3 verbs and subsystems.
Tests deliberately stay in the foyer when possible to avoid interleaving
with the ghost NPC's broadcasts in the library.
"""
import time

import pytest

from conftest import MUDServer, _free_port, lines


class TestChatAndDescription:
    def test_say_broadcasts_to_room_and_describe_me_changes_look(self, stage3_server_quiet):
        """Golden path for `say` and `describe me`.

        - alice and bob are both in the foyer.
        - alice says "hello bob": bob receives 'alice says, "hello bob"'.
        - alice describes herself: bob's `look alice` returns the custom
          description (not the Stage 2 generic line).
        - alice clears her description: `look alice` reverts to the
          generic line.
        """
        alice, _ = stage3_server_quiet.connect("alice")
        bob, _ = stage3_server_quiet.connect("bob")
        alice.drain(settle=0.1)  # consume bob's arrival broadcast

        # Default state: bob looks at alice — generic line, no description set.
        resp = bob.cmd("look alice")
        assert "alice is another adventurer." in lines(resp), \
            f"With no description set, expected generic line, got: {resp!r}"

        # alice speaks; bob hears.
        resp = alice.cmd('say "hello bob"')
        # alice's own response: 'You say, "hello bob"'
        assert any('You say, "hello bob"' in l for l in lines(resp)), \
            f"alice's say response should echo, got: {resp!r}"

        bc = bob.drain(settle=0.15)
        assert 'alice says, "hello bob"' in bc, \
            f"bob should receive alice's say broadcast, got: {bc!r}"

        # alice sets a description.
        resp = alice.cmd('describe me "a tall woman with a red cloak"')
        assert "Your description is set." in lines(resp), \
            f"describe me success line, got: {resp!r}"

        # No broadcast for describe me.
        leaked = bob.drain(settle=0.1)
        assert leaked == "", \
            f"describe me must not broadcast, got: {leaked!r}"

        # bob's look at alice now returns the custom description.
        resp = bob.cmd("look alice")
        body = " ".join(lines(resp))
        assert "tall woman with a red cloak" in body, \
            f"After describe me, look should return custom description, got: {resp!r}"
        assert "another adventurer" not in body, \
            f"Custom description should replace the generic line, got: {resp!r}"

        # alice clears her description.
        resp = alice.cmd('describe me ""')
        assert "Your description is cleared." in lines(resp), \
            f"Empty describe me should clear, got: {resp!r}"

        # bob's look at alice reverts to the generic line.
        resp = bob.cmd("look alice")
        assert "alice is another adventurer." in lines(resp), \
            f"After clear, look should return generic line, got: {resp!r}"


class TestGraffitiPersistence:
    def test_inscription_visible_in_room_and_survives_restart(self, stage3_server_quiet):
        """Golden path for persistent graffiti.

        - alice writes on the stone plaque in the library.
        - alice's `look plaque` shows the inscription appended to the
          object's description, prefixed by `Scrawled by alice: `.
        - bob (a different player) walks to the library and sees the
          same inscription.
        - The server is restarted on the same port. A NEW client connects
          and looks at the plaque — the inscription is STILL there,
          loaded from `graffiti.json`.
        """
        # Phase 1: write the inscription on the original server.
        alice, _ = stage3_server_quiet.connect("alice")
        bob, _ = stage3_server_quiet.connect("bob")
        alice.drain(settle=0.1)

        # alice walks to the library and writes on the plaque.
        resp = alice.cmd("east")
        assert "Library" in lines(resp)[0]
        # The library has the ghost; drain it.
        alice.drain(settle=0.1)

        resp = alice.cmd('write "alice was here" on plaque')
        assert "You write on the stone plaque." in lines(resp), \
            f"Write success line, got: {resp!r}"

        # alice's own look at the plaque shows the inscription.
        resp = alice.cmd("look plaque")
        body = lines(resp)
        assert any("Scrawled by alice: alice was here" in l for l in body), \
            f"Inscription should appear under description, got: {resp!r}"
        # And the description itself is still on the first line.
        assert any("weathered stone plaque" in l for l in body), \
            f"Description should still be present, got: {resp!r}"

        # bob walks to the library and looks at the plaque too.
        resp = bob.cmd("east")
        assert "Library" in lines(resp)[0]
        bob.drain(settle=0.1)

        resp = bob.cmd("look plaque")
        assert any("Scrawled by alice: alice was here" in l for l in lines(resp)), \
            f"bob should see alice's inscription, got: {resp!r}"

        # Capture the port so we can restart on the same port. (The
        # original server will be torn down by the fixture afterward,
        # but we shut it down now to free the port.)
        port = stage3_server_quiet.port
        cmd = stage3_server_quiet.cmd_line
        stage3_server_quiet.close()

        # Phase 2: NEW server on the same port. Inscription should load
        # from graffiti.json and still be visible.
        srv2 = MUDServer(cmd, port, extra_args="--tick-seconds 0.3")
        try:
            carol, _ = srv2.connect("carol")
            carol.cmd("east")  # to library
            carol.drain(settle=0.1)
            resp = carol.cmd("look plaque")
            assert any("Scrawled by alice: alice was here" in l for l in lines(resp)), \
                f"Inscription must persist across server restart, got: {resp!r}"
        finally:
            srv2.close()


class TestNPCHeartbeat:
    def test_ghost_executes_script_on_ticks(self, stage3_server):
        """Golden path for NPC scripts.

        The ghost NPC starts in the library with a scripted loop:
            0: say "Arell... where is Arell..."
            1: emote "drifts slowly toward the shelves"
            2: wait
            3: move west (to foyer)
            4: say "The foyer is colder than I remember."
            5: wait
            6: move east (back to library)

        With --tick-seconds 0.3, alice (in the library) observes the
        ghost's say/emote broadcasts and a movement broadcast within a
        few seconds. We don't pin down the exact tick the ghost is on
        when alice arrives (it depends on subprocess startup timing); we
        just verify the script is alive — speech, an emote, and a move
        broadcast all appear within a generous window.
        """
        # Connect alice and walk her to the library where the ghost lives.
        alice, _ = stage3_server.connect("alice")
        resp = alice.cmd("east")
        assert "Library" in lines(resp)[0]

        # The ghost should appear in `Also here:`. Its canonical name is
        # "pale ghost".
        also = next((l for l in lines(resp) if l.startswith("Also here:")), "")
        # Note: ghost may or may not appear depending on whether it's
        # currently in the library or has moved to the foyer. We accept
        # either, but check via repeated look over the cycle.

        # look the ghost (it may be there or in foyer right now).
        # If it is here, we get its description.
        # If not, we get a no-such-target line. Either is fine here.

        # Now collect 6 seconds of broadcast traffic. With tick=0.3s
        # that's ~20 ticks, more than enough for the 7-step script
        # to wrap around at least twice.
        deadline = time.time() + 6.0
        accumulated = ""
        while time.time() < deadline:
            chunk = alice.drain(settle=0.3)
            if chunk:
                accumulated += chunk

        # We must have observed the ghost speak (matches script step 0
        # or step 4).
        assert ('pale ghost says, "' in accumulated), \
            f"Expected ghost speech broadcast in {accumulated!r}"

        # We must have observed the ghost emote (script step 1).
        assert ("pale ghost drifts slowly toward the shelves." in accumulated), \
            f"Expected ghost emote broadcast in {accumulated!r}"

        # We must have observed at least one ghost movement broadcast.
        # Either departure (leaves to the west) or arrival (arrives from
        # the east) — alice sees the corresponding side based on which
        # room she's in.
        moved = ("pale ghost leaves to the west." in accumulated
                 or "pale ghost arrives from the east." in accumulated
                 or "pale ghost arrives from the west." in accumulated
                 or "pale ghost leaves to the east." in accumulated)
        assert moved, \
            f"Expected at least one ghost movement broadcast in {accumulated!r}"


