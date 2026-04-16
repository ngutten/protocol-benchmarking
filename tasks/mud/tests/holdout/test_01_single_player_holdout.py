"""Stage 1 holdout tests: edge cases and ambiguity probes.

These exercise behaviors that are specified but subtle — room-level light
evaluation, toggle-state persistence across pickup/drop, look targeting in
dark rooms, object ordering, alias resolution across room and inventory.
"""
import pytest

from conftest import lines


def _you_see(resp):
    """Return the 'You see: ...' line of a response, or '' if absent."""
    return next((l for l in lines(resp) if l.startswith("You see:")), "")


def _exits_line(resp):
    return next((l for l in lines(resp) if l.startswith("Exits:")), "")


def _descend_with_lit_lantern_off(session):
    """Helper: take lantern + key, unlock grate, descend to cellar.

    Leaves the session in the cellar with an UNLIT lantern in inventory and
    the sword still in the room.
    """
    session.cmd("take lantern")
    session.cmd("take key")
    session.cmd("east")
    session.cmd("use key")
    resp = session.cmd("down")
    assert "Cellar" in lines(resp)[0]


class TestLightSourceTransitions:
    def test_light_source_survives_drop_and_room_visit(self, session):
        """A lit lantern dropped in a dark room keeps the room lit for
        observers (including the returning player), and its toggle state
        persists across pickup/drop cycles.
        """
        _descend_with_lit_lantern_off(session)

        # Cellar is dark (unlit lantern in inventory doesn't count).
        resp = session.cmd("look")
        joined = "\n".join(lines(resp))
        assert "pitch" in joined.lower(), \
            f"Cellar with unlit lantern should be dark, got: {resp!r}"

        # look <inventory item> still works in dark
        resp = session.cmd("look lantern")
        assert "brass" in " ".join(lines(resp)).lower()

        # Light the lantern; cellar becomes lit, sword visible
        session.cmd("use lantern")
        resp = session.cmd("look")
        assert any("stone bench" in l for l in lines(resp)), \
            "Cellar should show lit description after lighting lantern"
        assert "tarnished sword" in _you_see(resp)

        # Drop the (lit) lantern — room stays lit because the lantern is
        # now in the room's object list, still toggled on.
        session.cmd("drop lantern")
        resp = session.cmd("look")
        assert any("stone bench" in l for l in lines(resp)), \
            "Cellar should remain lit: lit lantern is now in room objects"
        you_see = _you_see(resp)
        assert "brass lantern" in you_see and "tarnished sword" in you_see

        # Leave and return — the cellar should still be lit.
        resp = session.cmd("up")
        assert "Library" in lines(resp)[0]
        resp = session.cmd("down")
        assert any("stone bench" in l for l in lines(resp)), \
            "After leaving and returning, cellar should still be lit (lantern still on in room)"

        # Pick the lantern up again — state preserved, still lit.
        session.cmd("take lantern")
        resp = session.cmd("look")
        assert any("stone bench" in l for l in lines(resp)), \
            "Cellar should still be lit — lit lantern now back in inventory"

        # Toggle it off from inventory while still in the dark cellar.
        resp = session.cmd("use lantern")
        assert any("snuff" in l.lower() or "off" in l.lower() or "extinguish" in l.lower()
                   or "shadows fold" in l.lower() for l in lines(resp)), \
            f"Expected off-message from lantern toggle, got: {resp!r}"

        # Room is now dark again.
        resp = session.cmd("look")
        joined = "\n".join(lines(resp))
        assert "pitch" in joined.lower(), \
            f"Cellar should return to dark after turning lantern off, got: {resp!r}"
        # And the sword is no longer visible in the dark-room output
        assert not any(l.startswith("You see:") for l in lines(resp))


class TestAddressingAndIsolation:
    def test_world_ids_and_cross_room_targets_are_unreachable(self, session):
        """Objects are addressed by canonical name or alias only, and only
        while the player is in the same room. World ids (the keys of the
        `objects` map in world.json) are not legal addresses, and neither
        are items sitting in a room the player is not currently in.
        """
        # World id rejection: "rusted_key" (underscore) is the object's id
        # in world.json but not its name ("rusted key") or alias ("key").
        resp = session.cmd("take rusted_key")
        out = lines(resp)
        assert any("no rusted_key here" in l.lower() for l in out), \
            f"World id should not address an object, got: {resp!r}"

        # Canonical name and alias both work
        assert "Taken." in lines(session.cmd("take rusted key"))
        session.cmd("drop rusted key")  # put it back
        assert "Taken." in lines(session.cmd("take key"))
        session.cmd("drop key")

        # Walk east to the library, leaving lantern, key, and (obviously)
        # sword + potion all behind us.
        resp = session.cmd("east")
        assert "Library" in lines(resp)[0]

        # The lantern is in the foyer. From the library, it is unreachable
        # by take, look, or use. All three produce the same "no lantern here"
        # line — the player has no handle on it at all.
        for verb in ("take", "look", "use"):
            resp = session.cmd(f"{verb} lantern")
            out = lines(resp)
            assert any("no lantern here" in l.lower() for l in out), \
                f"`{verb} lantern` from library should be unreachable, got: {resp!r}"

        # Sword is in the cellar — even more remote. Same result.
        for verb in ("take", "look", "use"):
            resp = session.cmd(f"{verb} sword")
            out = lines(resp)
            assert any("no sword here" in l.lower() for l in out), \
                f"`{verb} sword` from library should be unreachable, got: {resp!r}"

        # Plaque IS in the library, so it DOES resolve — but with the
        # non-portable rejection rather than the no-such-target rejection.
        # This confirms we're distinguishing "not present" from "present
        # but refused".
        resp = session.cmd("take plaque")
        out = lines(resp)
        assert any("can't take the stone plaque" in l.lower() for l in out), \
            f"Plaque should give non-portable rejection, got: {resp!r}"


class TestKeyMatchingAmbiguity:
    def test_wrong_key_does_not_unlock_and_ambiguous_key_falls_through(self, session):
        """Two objects share the alias `key`: the rusted key (which unlocks
        the grate) and the garden key (which does not). The spec's unlock
        rule checks the TARGETED object's id — it does not search other
        matching keys. If the alias resolves to the wrong key, unlock fails,
        even when the correct key is also present.
        """
        # Step 1: pick up ONLY the garden key first.
        resp = session.cmd("north")
        assert "Overgrown Garden" in lines(resp)[0]
        assert "Taken." in lines(session.cmd("take garden key"))

        # Go back and across to the library — carrying only the garden key.
        session.cmd("south")
        resp = session.cmd("east")
        assert "Library" in lines(resp)[0]

        # `use key` resolves to garden_key (only one in inventory). Because
        # locked_by on the down exit is rusted_key (not garden_key), the
        # unlock rule fails and execution falls through to the use_effect.
        resp = session.cmd("use key")
        joined = " ".join(lines(resp)).lower()
        assert "fits no lock" in joined or "turns freely" in joined or \
               "no lock here" in joined, \
            f"Expected wrong-key fall-through message, got: {resp!r}"
        # And no unlock line appeared — crucial, this is the contentful
        # difference versus the correct key.
        assert not any("unlock" in l.lower() for l in lines(resp)), \
            f"Garden key must not produce an unlock line, got: {resp!r}"

        # Grate is still locked: going down produces the locked message.
        resp = session.cmd("down")
        assert any("padlocked" in l.lower() for l in lines(resp)), \
            f"Grate should still be locked after wrong-key use, got: {resp!r}"

        # Step 2: the player trying `use rusted key` cannot invoke it —
        # they don't have it, and it's not in the library.
        resp = session.cmd("use rusted key")
        assert any("no rusted key here" in l.lower() for l in lines(resp)), \
            f"Rusted key is not in reach, got: {resp!r}"

        # Step 3: fetch the rusted key and return. Now both keys are in
        # inventory, with garden_key first (earlier acquired).
        session.cmd("west")  # foyer
        assert "Taken." in lines(session.cmd("take rusted key"))
        session.cmd("east")  # library

        # `use key` STILL resolves to garden_key (inventory acquisition
        # order, first match wins). Unlock rule checks garden_key.id, which
        # is not `rusted_key`, so it still falls through.
        resp = session.cmd("use key")
        joined = " ".join(lines(resp)).lower()
        assert "fits no lock" in joined or "turns freely" in joined, \
            f"Ambiguous `use key` should still match garden_key first, got: {resp!r}"
        assert not any("unlock" in l.lower() for l in lines(resp)), \
            f"Garden key must not unlock even with rusted key also in inventory, got: {resp!r}"

        # Grate STILL locked.
        resp = session.cmd("down")
        assert any("padlocked" in l.lower() for l in lines(resp)), \
            "Grate remains locked until player explicitly names the rusted key"

        # Step 4: disambiguate with the full canonical name. Now unlock fires.
        resp = session.cmd("use rusted key")
        assert any("You unlock the way down." in l for l in lines(resp)), \
            f"Expected unlock line via canonical name, got: {resp!r}"

        # Now the grate is open.
        resp = session.cmd("down")
        assert "Cellar" in lines(resp)[0]


class TestDarkRoomLookSpecifics:
    def test_look_in_dark_distinguishes_inventory_room_and_missing(self, session):
        """In an unlit dark room, `look` targets are handled three ways:

        - inventory targets return their description normally (you feel
          what you're carrying)
        - room targets return 'It is too dark to see.'
        - targets that don't resolve anywhere also return 'It is too dark
          to see.' — darkness hides absence, not just presence

        Spec: stages/01_single_player.md, "look <target>" in the
        Darkness and Light section.
        """
        # Setup: key + lantern (off) in inventory, descend to dark cellar.
        session.cmd("take key")
        session.cmd("take lantern")
        session.cmd("east")
        session.cmd("use key")
        resp = session.cmd("down")
        assert "Cellar" in lines(resp)[0]

        # Bare `look` shows the dark form: name + dark_description only.
        resp = session.cmd("look")
        out = lines(resp)
        assert "Cellar" in out[0]
        joined = "\n".join(out).lower()
        assert "pitch" in joined, f"Expected dark cellar description, got: {resp!r}"
        assert not any(l.startswith("Exits:") for l in out), \
            "Dark room look should omit Exits line"
        assert not any(l.startswith("You see:") for l in out), \
            "Dark room look should omit You see line"
        # And the lit-form description ("stone bench") must not leak.
        assert "stone bench" not in joined

        # Inventory targets still resolve — the player knows what they hold.
        resp = session.cmd("look lantern")
        desc = " ".join(lines(resp)).lower()
        assert "brass" in desc or "tarnished" in desc, \
            f"Inventory look should return lantern description in dark, got: {resp!r}"
        # And the "too dark" phrase must NOT appear for an inventory hit.
        assert "too dark" not in desc, \
            f"Inventory look should not be blocked by darkness, got: {resp!r}"

        # Room target (sword is in cellar, not in inventory).
        resp = session.cmd("look sword")
        out = lines(resp)
        assert any("too dark to see" in l.lower() for l in out), \
            f"Room-object look in dark should be blocked, got: {resp!r}"

        # Target that doesn't resolve anywhere — spec says dark-room
        # response is "It is too dark to see." (absence hidden by darkness),
        # NOT "There is no potion here."
        resp = session.cmd("look potion")
        out = lines(resp)
        assert any("too dark to see" in l.lower() for l in out), \
            f"Missing target in dark room should still say 'too dark', got: {resp!r}"
        assert not any("no potion here" in l.lower() for l in out), \
            f"Dark-room absence should not reveal which objects are missing, got: {resp!r}"

        # Sanity check: after lighting the lantern, the same three
        # queries behave differently. `look sword` now works; `look
        # potion` now gives the no-such-target response.
        session.cmd("use lantern")
        resp = session.cmd("look sword")
        assert "tarnished" in " ".join(lines(resp)).lower(), \
            f"After lighting, look sword should work, got: {resp!r}"
        resp = session.cmd("look potion")
        assert any("no potion here" in l.lower() for l in lines(resp)), \
            f"After lighting, absent target should give no-such-target, got: {resp!r}"


class TestInputNormalization:
    def test_case_whitespace_empty_and_unknown(self, session):
        """Input normalization is specified up front: case-insensitive,
        internal whitespace collapsed, leading/trailing whitespace stripped.
        Empty input yields a bare prompt (no body), and unknown commands
        yield the canonical rejection. These are low-level but pervasive;
        inconsistent handling across verbs is a common bug.
        """
        # Case insensitivity across mixed cases and a multi-word argument.
        # All three variants should take the brass lantern successfully.
        for cmd in ("TAKE LANTERN", "Take Lantern", "take lantern"):
            # Fresh session per variant so each one is tested from scratch.
            from conftest import MUDSession
            import os
            s = MUDSession(os.environ.get("ENGINE_CMD", "python3 mud.py"))
            try:
                resp = s.cmd(cmd)
                assert "Taken." in lines(resp), \
                    f"Variant {cmd!r} should succeed, got: {resp!r}"
            finally:
                s.close()

        # Remainder of the assertions reuse the outer session, which still
        # has the brass lantern in the foyer (we haven't taken anything).
        # Multi-space input: internal runs of spaces should collapse, so
        # "take   brass   lantern" is equivalent to "take brass lantern".
        resp = session.cmd("take   brass   lantern")
        assert "Taken." in lines(resp), \
            f"Multi-space input should collapse, got: {resp!r}"

        # Leading / trailing whitespace: stripped before parsing.
        resp = session.cmd("   drop lantern   ")
        assert "Dropped." in lines(resp), \
            f"Leading/trailing whitespace should be stripped, got: {resp!r}"

        # Empty input: no response body, just a fresh prompt. MUDSession's
        # cmd() returns the body between the previous prompt and the next,
        # so for an empty input the return should be the empty string.
        resp = session.cmd("")
        assert resp == "", \
            f"Empty input should produce no body, got: {resp!r}"

        # Whitespace-only input collapses to empty too.
        resp = session.cmd("     ")
        assert resp == "", \
            f"Whitespace-only input should produce no body, got: {resp!r}"

        # Unknown command: canonical rejection.
        resp = session.cmd("frobnicate the widget")
        assert "I don't understand that." in lines(resp), \
            f"Unknown command should give canonical rejection, got: {resp!r}"

        # Case of the unknown command doesn't change the outcome.
        resp = session.cmd("FROBNICATE THE WIDGET")
        assert "I don't understand that." in lines(resp), \
            f"Uppercase unknown command should still reject, got: {resp!r}"


class TestNoPrefixMatching:
    def test_partial_names_do_not_match(self, session):
        """Object matching is whole-string equality against canonical name
        or alias — not prefix, not substring. Many MUD engines are lenient
        here, so a faithful-looking reference can still get this wrong.

        The rusted key has name 'rusted key' and alias 'key'. 'rusted'
        alone is a prefix of the name but not an alias; it must not match.
        Same for partial matches against the lantern and the plaque.
        """
        # In the foyer, the rusted key is present. Both the canonical name
        # and the alias work; the prefix alone does not.
        assert "Taken." in lines(session.cmd("take rusted key"))
        session.cmd("drop rusted key")
        assert "Taken." in lines(session.cmd("take key"))
        session.cmd("drop key")

        # Prefix of the name — must NOT match.
        resp = session.cmd("take rusted")
        out = lines(resp)
        assert any("no rusted here" in l.lower() for l in out), \
            f"'take rusted' must not prefix-match 'rusted key', got: {resp!r}"
        assert "Taken." not in out, \
            f"'take rusted' must not succeed, got: {resp!r}"

        # Substring of the name — must NOT match either.
        resp = session.cmd("take usted")
        assert any("no usted here" in l.lower() for l in lines(resp)), \
            f"'take usted' must not substring-match 'rusted key', got: {resp!r}"

        # Now with the rusted key actually held, `use rusted` must still
        # fail — it cannot unlock, because it does not address any object.
        session.cmd("take key")  # take rusted key into inventory
        session.cmd("east")      # library, where the locked grate lives
        resp = session.cmd("use rusted")
        assert any("no rusted here" in l.lower() for l in lines(resp)), \
            f"'use rusted' must not prefix-match the held rusted key, got: {resp!r}"
        # And the grate stays locked.
        resp = session.cmd("down")
        assert any("padlocked" in l.lower() for l in lines(resp)), \
            "Grate must remain locked — no prefix-match unlocks it"

        # look <partial> on a room object behaves the same way.
        resp = session.cmd("look stone")  # plaque's canonical name is 'stone plaque'
        assert any("no stone here" in l.lower() for l in lines(resp)), \
            f"'look stone' must not prefix-match 'stone plaque', got: {resp!r}"
        # And the exact form works.
        resp = session.cmd("look stone plaque")
        desc = " ".join(lines(resp))
        assert "plaque" in desc.lower(), \
            f"'look stone plaque' (full name) should match, got: {resp!r}"


