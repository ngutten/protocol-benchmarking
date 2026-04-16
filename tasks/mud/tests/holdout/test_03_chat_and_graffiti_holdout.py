"""Stage 3 holdout tests: edge cases, security probes, and ambiguity tests
for chat, graffiti, descriptions, and NPCs.
"""
import time

import pytest

from conftest import MUDServer, lines


class TestGraffitiSpecialContent:
    def test_inscription_with_special_chars_roundtrips_across_restart(self, stage3_server_quiet):
        """Spec says inscription text may contain any UTF-8 character
        except `"` and a literal newline. That includes backslashes,
        non-ASCII characters, multi-byte emoji, control chars, etc. All
        of these must:
          1. Be preserved verbatim in `look <object>` output
          2. Be persisted in graffiti.json without corrupting the file
          3. Be reloaded correctly on the next server start

        This catches implementations that naively format the inscription
        into an f-string at save time, or that store text in a file
        format that doesn't quote/escape properly.
        """
        # Inscriptions to test. Each must contain only allowed chars
        # (no `"`, no newline) — but otherwise stresses encoding paths.
        inscriptions = [
            "back\\slash and a tab\there",      # backslash + tab
            "unicode héllo 世界 🎩",              # multi-byte UTF-8
            "control \x07 \x1b\x5b1m chars",     # BEL and ESC[ (control)
            "spaces   in   middle",             # multi-space (NOT collapsed for text)
            "punct: !@#$%^&*(){}[]<>?,./|`~+=", # ASCII punctuation
        ]

        # alice writes them all on the plaque in the library.
        alice, _ = stage3_server_quiet.connect("alice")
        alice.cmd("east")
        alice.drain(settle=0.1)  # ghost broadcasts

        for text in inscriptions:
            resp = alice.cmd(f'write "{text}" on plaque')
            assert "You write on the stone plaque." in lines(resp), \
                f"write should succeed for {text!r}, got: {resp!r}"

        # alice's look plaque should now show all five inscriptions in
        # write order.
        resp = alice.cmd("look plaque")
        body = "\n".join(lines(resp))
        for text in inscriptions:
            expected = f"Scrawled by alice: {text}"
            assert expected in body, \
                f"Expected inscription line {expected!r} not found in {body!r}"

        # Restart the server on the same port; the inscriptions must
        # come back exactly as written.
        port = stage3_server_quiet.port
        cmd = stage3_server_quiet.cmd_line
        stage3_server_quiet.close()

        srv2 = MUDServer(cmd, port, extra_args="--tick-seconds 0.3")
        try:
            bob, _ = srv2.connect("bob")
            bob.cmd("east")
            bob.drain(settle=0.1)

            resp = bob.cmd("look plaque")
            body = "\n".join(lines(resp))
            for text in inscriptions:
                expected = f"Scrawled by alice: {text}"
                assert expected in body, (
                    f"After restart, inscription {expected!r} did not survive. "
                    f"Body: {body!r}"
                )
        finally:
            srv2.close()

    def test_long_inscription_works_and_persists(self, stage3_server_quiet):
        """A multi-kilobyte inscription should be writable, displayable,
        and persistable. Spec doesn't cap inscription length, so this
        verifies an implementation hasn't silently truncated.
        """
        long_text = "x" * 4000  # 4 KB of one character

        alice, _ = stage3_server_quiet.connect("alice")
        alice.cmd("east")
        alice.drain(settle=0.1)

        resp = alice.cmd(f'write "{long_text}" on plaque', timeout=5.0)
        assert "You write on the stone plaque." in lines(resp), \
            f"Long write should succeed, got: {resp!r}"

        resp = alice.cmd("look plaque", timeout=5.0)
        body = "\n".join(lines(resp))
        assert f"Scrawled by alice: {long_text}" in body, \
            "Long inscription should appear verbatim in look output"

        # Persistence
        port = stage3_server_quiet.port
        cmd = stage3_server_quiet.cmd_line
        stage3_server_quiet.close()
        srv2 = MUDServer(cmd, port, extra_args="--tick-seconds 0.3")
        try:
            bob, _ = srv2.connect("bob")
            bob.cmd("east")
            bob.drain(settle=0.1)
            resp = bob.cmd("look plaque", timeout=5.0)
            body = "\n".join(lines(resp))
            assert f"Scrawled by alice: {long_text}" in body, \
                "Long inscription must survive restart"
        finally:
            srv2.close()


class TestConsumableGraffiti:
    def test_write_then_consume_does_not_crash(self, stage3_server_quiet):
        """Writing on a portable consumable (the health potion) and then
        using it (which consumes it) must not crash the server. The
        consumed object disappears from the world; subsequent attempts
        to target it produce the standard no-such-target response.

        This pins behavior at the awkward intersection of
        write/persistence and use/consumed.
        """
        alice, _ = stage3_server_quiet.connect("alice")

        # Walk to garden, take the potion.
        resp = alice.cmd("north")
        assert "Overgrown Garden" in lines(resp)[0]
        assert "Taken." in lines(alice.cmd("take potion"))

        # Write on the potion (in inventory; spec allows inventory targets).
        resp = alice.cmd('write "drink me" on potion')
        assert "You write on the health potion." in lines(resp), \
            f"Write on inventory potion should work, got: {resp!r}"

        # look potion shows description + inscription.
        resp = alice.cmd("look potion")
        body = "\n".join(lines(resp))
        assert "vial of dark red liquid" in body, \
            f"Description should still appear, got: {resp!r}"
        assert "Scrawled by alice: drink me" in body, \
            f"Inscription should appear, got: {resp!r}"

        # Use (drink) the potion — it is consumed.
        resp = alice.cmd("use potion")
        assert "drink the potion" in " ".join(lines(resp)).lower(), \
            f"Potion use-effect should fire, got: {resp!r}"

        # Now the potion is gone. Look should report no such target.
        resp = alice.cmd("look potion")
        assert "There is no potion here." in lines(resp), \
            f"After consumption, look potion should say no such target, got: {resp!r}"

        # Inventory no longer lists it.
        resp = alice.cmd("inventory")
        assert "health potion" not in lines(resp)[0], \
            f"Consumed potion should be gone from inventory, got: {resp!r}"

        # And the server is still alive — basic command works.
        resp = alice.cmd("look")
        assert "Overgrown Garden" in lines(resp)[0]


class TestWriteInDarkRoom:
    def test_write_on_room_object_blocked_in_dark_inventory_still_works(self, stage3_server_quiet):
        """In an unlit dark room, write on a ROOM object is blocked
        ('It is too dark to see.') — the same rule as look/take/use.
        Inventory writes still work, since the player can scribble on
        what they hold.
        """
        alice, _ = stage3_server_quiet.connect("alice")

        # Setup: take key, lantern, and the OLD BOOK (we'll write on it
        # both from inventory and after dropping it in the dark cellar).
        alice.cmd("take key")
        alice.cmd("take lantern")
        alice.cmd("east")  # library
        alice.cmd("take book")
        alice.cmd("use key")
        alice.cmd("down")  # cellar (dark; lantern is OFF in inventory)

        # Cellar is dark. Confirm by looking.
        resp = alice.cmd("look")
        joined = "\n".join(lines(resp))
        assert "pitch" in joined.lower(), \
            f"Cellar should be dark, got: {resp!r}"

        # Drop the book here so it becomes a room object in the dark.
        assert "Dropped." in lines(alice.cmd("drop book"))

        # Try to write on the book (now in the dark cellar's object list).
        # Spec: must produce "It is too dark to see." — not the success
        # line, not "no book here".
        resp = alice.cmd('write "in the dark" on book')
        assert "It is too dark to see." in lines(resp), \
            f"Write on room object in dark must be blocked, got: {resp!r}"
        # And no success line.
        assert not any("write on" in l.lower() for l in lines(resp)), \
            f"Write must not have succeeded, got: {resp!r}"

        # Inventory write still works in the dark — write on the lantern
        # (which we are still carrying).
        resp = alice.cmd('write "still mine" on lantern')
        assert "You write on the brass lantern." in lines(resp), \
            f"Write on inventory item should work in dark, got: {resp!r}"

        # And the missing-target case in dark also gives the dark line.
        resp = alice.cmd('write "test" on potion')
        assert "It is too dark to see." in lines(resp), \
            f"Missing target in dark should give too-dark, got: {resp!r}"

        # Now light the lantern. Cellar becomes lit. Pick book back up
        # and drop again so it's a room object once more, then write
        # — should succeed in the lit room.
        alice.cmd("use lantern")
        alice.cmd("take book")
        alice.cmd("drop book")
        resp = alice.cmd('write "now I can see" on book')
        assert "You write on the old book." in lines(resp), \
            f"Write on room object should work once room is lit, got: {resp!r}"


class TestNPCBlockedByLock:
    def test_adventurer_stays_in_library_while_grate_locked(self, stage3_server):
        """The confused adventurer's script includes `move down`. While
        the library→cellar grate is locked, that action must silently
        no-op every cycle: the adventurer never moves, no leave/arrive
        broadcasts fire for that direction.

        Spec: 'If the exit is missing, or the direction is not one of
        the six valid names, or the exit is locked: the action is
        skipped silently.'
        """
        alice, _ = stage3_server.connect("alice")
        resp = alice.cmd("east")
        assert "Library" in lines(resp)[0]

        # Adventurer should be in the library (Also here lists him).
        also = next((l for l in lines(resp) if l.startswith("Also here:")), "")
        assert "confused adventurer" in also, \
            f"Adventurer should be in library at start, got: {resp!r}"

        # Collect 4 seconds of broadcasts (~13 ticks at 0.3s) — every
        # script cycle (5 steps) hits `move down` once, so several
        # blocked-move attempts will occur in this window.
        deadline = time.time() + 4.0
        accumulated = ""
        while time.time() < deadline:
            chunk = alice.drain(settle=0.3)
            if chunk:
                accumulated += chunk

        # The adventurer must NEVER have left to the down direction.
        assert "confused adventurer leaves to the down" not in accumulated, (
            "Adventurer must not move through a locked exit; "
            f"got broadcast traffic: {accumulated!r}"
        )

        # And the adventurer must still be in the library.
        resp = alice.cmd("look")
        also = next((l for l in lines(resp) if l.startswith("Also here:")), "")
        assert "confused adventurer" in also, \
            f"Adventurer should still be in library after 4s, got: {resp!r}"

    def test_adventurer_descends_after_player_unlocks_grate(self, stage3_server):
        """Once the player unlocks the grate, the next time the
        adventurer's script ticks `move down` the move succeeds. The
        adventurer then disappears from the library and lands in the
        cellar, and a leave broadcast fires.
        """
        alice, _ = stage3_server.connect("alice")
        # Player unlocks the grate.
        assert "Taken." in lines(alice.cmd("take key"))
        alice.cmd("east")  # library
        alice.drain(settle=0.5)  # consume initial NPC noise
        resp = alice.cmd("use key")
        assert "You unlock the way down." in lines(resp), \
            f"Expected unlock line, got: {resp!r}"

        # Wait long enough for the adventurer's script to cycle through
        # `move down` at least once. With a 5-step script and 0.3s
        # ticks, that's ~1.5s per cycle; 4s gives ~2.5 cycles.
        deadline = time.time() + 4.0
        accumulated = ""
        descended = False
        while time.time() < deadline:
            chunk = alice.drain(settle=0.3)
            if chunk:
                accumulated += chunk
                if "confused adventurer leaves to the down" in accumulated:
                    descended = True
                    break

        assert descended, (
            "After unlock, adventurer must descend on next move tick. "
            f"Accumulated broadcasts: {accumulated!r}"
        )

        # Adventurer is now no longer in the library.
        resp = alice.cmd("look")
        also = next((l for l in lines(resp) if l.startswith("Also here:")), "")
        assert "confused adventurer" not in also, \
            f"Adventurer should have left library, got: {resp!r}"

        # And we can find the adventurer in the cellar.
        # First take the lantern so we can see down there.
        alice.cmd("west")  # foyer
        alice.cmd("take lantern")
        alice.cmd("use lantern")  # light it (off by default)
        alice.cmd("east")  # library
        alice.drain(settle=0.4)
        resp = alice.cmd("down")
        # Cellar is now lit (we have a lit lantern).
        also = next((l for l in lines(resp) if l.startswith("Also here:")), "")
        assert "confused adventurer" in also, \
            f"Adventurer should be in cellar after descent, got: {resp!r}"


class TestMultiNPC:
    def test_both_npcs_run_independently(self, stage3_server):
        """Multiple NPCs share the world. Each runs its own script
        independently. While in the library, alice should observe both
        the ghost's and the adventurer's broadcasts within a few seconds.
        """
        alice, _ = stage3_server.connect("alice")
        alice.cmd("east")  # library

        # Collect ~5 seconds of broadcast traffic.
        deadline = time.time() + 5.0
        accumulated = ""
        while time.time() < deadline:
            chunk = alice.drain(settle=0.3)
            if chunk:
                accumulated += chunk

        # Ghost broadcasts: speech + emote.
        ghost_speech = 'pale ghost says, "' in accumulated
        ghost_emote = "pale ghost drifts slowly toward the shelves." in accumulated
        # Adventurer broadcasts: speech + emote.
        adv_speech = 'confused adventurer says, "' in accumulated
        adv_emote = "confused adventurer shuffles in a slow circle, peering at the floor." in accumulated

        assert ghost_speech or ghost_emote, \
            f"Expected ghost broadcast in {accumulated!r}"
        assert adv_speech or adv_emote, \
            f"Expected adventurer broadcast in {accumulated!r}"

    def test_npc_iteration_order_is_alphabetical_by_id(self, stage3_server):
        """Within a single tick, NPCs are processed in alphabetical order
        by NPC id. 'adventurer' < 'ghost', so the adventurer's action
        fires (and broadcasts) before the ghost's action in the same tick.

        Both NPCs have a `say` at script index 0, so on the first tick
        after alice arrives they both broadcast. The adventurer's bytes
        must reach alice's socket BEFORE the ghost's.
        """
        alice, _ = stage3_server.connect("alice")
        alice.cmd("east")

        # Collect ~3 seconds — definitely covers the first tick where
        # both NPCs are at script index 0.
        deadline = time.time() + 3.0
        accumulated = ""
        while time.time() < deadline:
            chunk = alice.drain(settle=0.3)
            if chunk:
                accumulated += chunk

        # First substring occurrence of each NPC's broadcast.
        idx_adv = accumulated.find("confused adventurer says")
        idx_ghost = accumulated.find("pale ghost says")

        assert idx_adv >= 0, \
            f"Adventurer never spoke in 3s window: {accumulated!r}"
        assert idx_ghost >= 0, \
            f"Ghost never spoke in 3s window: {accumulated!r}"
        assert idx_adv < idx_ghost, (
            "Per spec, NPCs iterate in alphabetical order by id. "
            "'adventurer' < 'ghost', so adventurer's say should come first. "
            f"Got adv at byte {idx_adv}, ghost at byte {idx_ghost}. "
            f"Buffer: {accumulated!r}"
        )
