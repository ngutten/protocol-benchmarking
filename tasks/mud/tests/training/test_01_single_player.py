"""Stage 1 training tests: the single-player text adventure is playable.

These are golden-path tests — they describe the game working as intended.
The first test is an end-to-end playthrough of the cellar puzzle: start in
the foyer, pick up the lantern and the key, head east to the library,
unlock the grate down, descend into the dark cellar, light the lantern to
see, grab the sword, and climb back out.

If this test passes, the core Stage 1 mechanics (look, movement, take,
use-as-toggle, use-as-unlock, darkness + light sources, aliases) are all
working end-to-end.
"""
import pytest

from conftest import lines


class TestGoldenPathPlaythrough:
    def test_full_cellar_puzzle(self, session):
        # --- Start in the foyer, welcome banner + initial room ---
        welcome_lines = lines(session.welcome)
        assert "Welcome." in welcome_lines
        assert "Foyer" in welcome_lines
        # Both foyer objects listed
        you_see = next((l for l in welcome_lines if l.startswith("You see:")), "")
        assert "brass lantern" in you_see
        assert "rusted key" in you_see

        # --- Pick up the lantern and the key (by alias) ---
        resp = session.cmd("take lantern")
        assert "Taken." in lines(resp)

        resp = session.cmd("get key")  # alias for take
        assert "Taken." in lines(resp)

        # Inventory reflects both items
        resp = session.cmd("inventory")
        inv_line = lines(resp)[0]
        assert "brass lantern" in inv_line
        assert "rusted key" in inv_line

        # Foyer's You see: line should now be absent (room is empty of objects)
        resp = session.cmd("look")
        assert not any(l.startswith("You see:") for l in lines(resp)), \
            f"Foyer should have no objects left, got: {resp!r}"

        # --- Move east to library via shortcut ---
        resp = session.cmd("e")
        out = lines(resp)
        assert "Library" in out
        assert any(l.startswith("Exits:") and "down" in l and "west" in l for l in out)

        # --- Try to go down: grate is locked ---
        resp = session.cmd("down")
        out = lines(resp)
        # Exact locked message from world.json
        assert any("padlocked" in l for l in out), \
            f"Expected locked-grate message, got: {resp!r}"
        # Should still be in the library
        resp = session.cmd("look")
        assert "Library" in lines(resp)[0]

        # --- Unlock with the key ---
        resp = session.cmd("use key")
        out = lines(resp)
        assert "You unlock the way down." in out

        # --- Descend into the dark cellar ---
        resp = session.cmd("down")
        out = lines(resp)
        assert "Cellar" in out[0]
        # Dark description visible, lit description (mentioning the sword) NOT visible
        joined = "\n".join(out)
        assert "pitch darkness" in joined or "pitch black" in joined.lower()
        assert "stone bench" not in joined, \
            "Cellar's lit description leaked while room should be dark"
        # No Exits or You see in the dark
        assert not any(l.startswith("Exits:") for l in out)
        assert not any(l.startswith("You see:") for l in out)

        # --- Light the lantern; room now reads as lit ---
        resp = session.cmd("use lantern")
        out = lines(resp)
        lit_msg = " ".join(out)
        assert "light" in lit_msg.lower(), f"Expected lantern-lighting message, got: {resp!r}"

        resp = session.cmd("look")
        out = lines(resp)
        assert "Cellar" in out[0]
        assert any("stone bench" in l for l in out), \
            "Expected the lit cellar description after lighting lantern"
        assert any(l.startswith("Exits:") and "up" in l for l in out)
        assert any(l.startswith("You see:") and "tarnished sword" in l for l in out)

        # --- Take the sword ---
        resp = session.cmd("take sword")
        assert "Taken." in lines(resp)

        # --- Return to the library ---
        resp = session.cmd("up")
        out = lines(resp)
        assert "Library" in out[0]

        # Sword is now in inventory alongside lantern and key
        resp = session.cmd("i")  # shortcut
        inv_line = lines(resp)[0]
        for item in ("brass lantern", "rusted key", "tarnished sword"):
            assert item in inv_line, f"Expected {item} in inventory, got: {inv_line!r}"


class TestDropAndPickup:
    def test_drop_leaves_object_in_room_and_take_returns_it(self, session):
        """A dropped object is indistinguishable from a world-authored one.

        Take the lantern from the foyer, walk east to the library, drop it,
        walk back to the foyer and back again, look — the lantern is in the
        library's object list. `look lantern` returns its description. It
        can be taken with the usual `Taken.` response.
        """
        # Take lantern in foyer
        assert "Taken." in lines(session.cmd("take lantern"))

        # Walk east to library
        resp = session.cmd("east")
        assert "Library" in lines(resp)[0]

        # Drop lantern
        assert "Dropped." in lines(session.cmd("drop lantern"))

        # Lantern should now be listed in the library's objects
        resp = session.cmd("look")
        you_see = next((l for l in lines(resp) if l.startswith("You see:")), "")
        assert "brass lantern" in you_see, \
            f"Dropped lantern should appear in library's You see: line, got {resp!r}"

        # Walk back to foyer and returning should still find the lantern
        assert "Foyer" in lines(session.cmd("west"))[0]
        resp = session.cmd("east")
        you_see = next((l for l in lines(resp) if l.startswith("You see:")), "")
        assert "brass lantern" in you_see, \
            "Dropped lantern should still be in library after leaving and returning"

        # look <lantern> from the room returns its description (object is visible)
        resp = session.cmd("look lantern")
        desc = " ".join(lines(resp))
        assert "brass" in desc.lower() or "tarnished" in desc.lower(), \
            f"Expected lantern description on look, got: {resp!r}"

        # Take it back
        assert "Taken." in lines(session.cmd("take lantern"))

        # Now the library no longer lists it
        resp = session.cmd("look")
        you_see = next((l for l in lines(resp) if l.startswith("You see:")), "")
        assert "brass lantern" not in you_see, \
            "Lantern should be back in inventory, not in room, after take"


class TestConsumableUse:
    def test_drinking_potion_consumes_it(self, session):
        """use on a consumed object prints its message and removes it.

        Walk to the garden, take the health potion, use it. The effect
        message is printed, the potion leaves the inventory, and a
        subsequent use can no longer target it.
        """
        # Go north to the garden
        resp = session.cmd("north")
        assert "Overgrown Garden" in lines(resp)[0]
        you_see = next((l for l in lines(resp) if l.startswith("You see:")), "")
        assert "health potion" in you_see

        # Take the potion (by alias)
        assert "Taken." in lines(session.cmd("take potion"))

        resp = session.cmd("inventory")
        assert "health potion" in lines(resp)[0]

        # Drink it — effect message appears
        resp = session.cmd("use potion")
        out = " ".join(lines(resp))
        # world.json: "You drink the potion. Warmth spreads..."
        assert "drink" in out.lower() or "warmth" in out.lower(), \
            f"Expected potion use-effect message, got: {resp!r}"

        # Potion is gone — inventory no longer lists it
        resp = session.cmd("inventory")
        inv_line = lines(resp)[0]
        assert "health potion" not in inv_line, \
            f"Consumed potion should be removed from inventory, got: {inv_line!r}"

        # Using it again: no such object anywhere
        resp = session.cmd("use potion")
        out = lines(resp)
        # Canonical form is "There is no <target> here." with target being
        # the user's normalized input ("potion"), per spec.
        assert any("no potion here" in l.lower() for l in out), \
            f"Expected no-such-object response after consumption, got: {resp!r}"

        # And the garden room no longer lists it either
        resp = session.cmd("look")
        assert not any(l.startswith("You see:") and "potion" in l for l in lines(resp)), \
            "Consumed potion should not reappear in the room"


class TestNonPortable:
    def test_cannot_take_the_plaque(self, session):
        """Non-portable objects refuse `take` but remain visible and lookable.

        The stone plaque in the library has `portable: false`. Attempting
        to take it should produce the fixed rejection string, and the
        plaque should remain in the room's object list and be describable
        via `look`.
        """
        # Walk to the library
        resp = session.cmd("east")
        assert "Library" in lines(resp)[0]

        # Plaque is listed in You see:
        you_see = next((l for l in lines(resp) if l.startswith("You see:")), "")
        assert "stone plaque" in you_see

        # look plaque returns its description
        resp = session.cmd("look plaque")
        desc = " ".join(lines(resp))
        assert "plaque" in desc.lower(), f"Expected plaque description, got: {resp!r}"

        # take plaque is refused — canonical name in the response
        resp = session.cmd("take plaque")
        out = lines(resp)
        assert any("can't take the stone plaque" in l.lower() for l in out), \
            f"Expected portable-false rejection with canonical name, got: {resp!r}"

        # Inventory is unchanged (nothing was taken)
        resp = session.cmd("inventory")
        assert "stone plaque" not in lines(resp)[0]
        assert "nothing" in lines(resp)[0].lower()

        # Plaque is still in the library after the failed take
        resp = session.cmd("look")
        you_see = next((l for l in lines(resp) if l.startswith("You see:")), "")
        assert "stone plaque" in you_see, \
            "Failed take should leave plaque in the room"

        # Same rejection with `get` alias
        resp = session.cmd("get plaque")
        assert any("can't take the stone plaque" in l.lower() for l in lines(resp)), \
            f"Expected same rejection via get alias, got: {resp!r}"
