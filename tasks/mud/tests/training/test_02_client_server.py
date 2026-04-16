"""Stage 2 training tests: multi-user server is playable.

Golden-path integration tests for the client/server split: login, two
players sharing a room, movement producing broadcasts, `who` listing
present players, disconnect cleanup.
"""
import pytest

from conftest import lines


class TestTwoPlayerGoldenPath:
    def test_two_players_see_each_other_and_broadcasts_on_move(self, server):
        """Two players log in, share the foyer, one moves east.

        - Alice logs in first: sees foyer with no `Also here:` line (no
          one else yet).
        - Bob logs in second: sees foyer with `Also here: alice`.
        - Alice, after Bob logs in, receives `bob arrives.` as a broadcast.
        - Alice's `look` now includes `Also here: bob`.
        - Alice moves east. Alice sees the library. Bob (still in foyer)
          receives `alice leaves to the east.`.
        - Bob's `look` no longer lists alice; alice is now alone in the
          library.
        """
        # Alice logs in.
        alice, alice_welcome = server.connect("alice")
        welcome_lines = lines(alice_welcome)
        assert "Welcome, alice." in welcome_lines
        assert "Foyer" in welcome_lines
        assert not any(l.startswith("Also here:") for l in welcome_lines), \
            f"Alice alone in foyer — no Also here: expected, got: {alice_welcome!r}"

        # Bob logs in second. His greeting should list alice as already here.
        bob, bob_welcome = server.connect("bob")
        bw = lines(bob_welcome)
        assert "Welcome, bob." in bw
        assert "Foyer" in bw
        also = next((l for l in bw if l.startswith("Also here:")), "")
        assert "alice" in also, \
            f"Bob should see alice in Also here, got: {bob_welcome!r}"

        # Alice should have received the arrival broadcast.
        alice_bc = alice.drain(settle=0.15)
        assert "bob arrives." in alice_bc, \
            f"Alice should have received 'bob arrives.' broadcast, got: {alice_bc!r}"

        # Alice's next look now shows bob.
        resp = alice.cmd("look")
        also = next((l for l in lines(resp) if l.startswith("Also here:")), "")
        assert "bob" in also, \
            f"Alice's look should list bob, got: {resp!r}"

        # Alice moves east.
        resp = alice.cmd("east")
        out = lines(resp)
        assert "Library" in out[0]
        # Alice alone in library — no Also here.
        assert not any(l.startswith("Also here:") for l in out), \
            f"Alice alone in library, no Also here expected: {resp!r}"

        # Bob receives the departure broadcast.
        bob_bc = bob.drain(settle=0.15)
        assert "alice leaves to the east." in bob_bc, \
            f"Bob should have received departure broadcast, got: {bob_bc!r}"

        # Bob's look no longer lists alice.
        resp = bob.cmd("look")
        assert not any(l.startswith("Also here:") for l in lines(resp)), \
            f"Alice has moved, Bob should no longer list her, got: {resp!r}"

    def test_who_lists_logged_in_players(self, server):
        """`who` returns every connected player, alphabetical, one per line."""
        alice, _ = server.connect("alice")
        bob, _ = server.connect("bob")
        # Let arrival broadcasts settle before issuing `who`.
        alice.drain(settle=0.05)

        # carol logs in after; alice issues who.
        carol, _ = server.connect("carol")
        alice.drain(settle=0.05)

        resp = alice.cmd("who")
        names = [l.strip() for l in lines(resp)]
        assert names == ["alice", "bob", "carol"], \
            f"who should list all three alphabetically, got: {resp!r}"

    def test_disconnect_drops_player_from_Also_here(self, server):
        """When bob disconnects, alice should see `bob disconnects.` and
        her next look should no longer mention bob.
        """
        alice, _ = server.connect("alice")
        bob, _ = server.connect("bob")
        alice.drain(settle=0.05)  # consume bob's arrival broadcast

        # Bob quits cleanly. `quit` ends the session (no trailing prompt),
        # so we use the client's quit helper rather than cmd().
        resp = bob.quit()
        assert "Goodbye." in lines(resp)

        # Alice receives the disconnect broadcast.
        bc = alice.drain(settle=0.15)
        assert "bob disconnects." in bc, \
            f"Alice should see bob's disconnect, got: {bc!r}"

        # Alice's look no longer lists bob.
        resp = alice.cmd("look")
        assert not any(l.startswith("Also here:") for l in lines(resp)), \
            f"Bob has disconnected; Alice's foyer should have no Also here, got: {resp!r}"


class TestSharedObjectsAndBroadcastScoping:
    def test_object_pickup_broadcasts_to_room_only(self, server):
        """Object state is shared per-room, and broadcasts respect the
        speaker's current room.

        - alice and bob both in the foyer.
        - alice takes the lantern: bob receives the pickup broadcast and
          his next look no longer shows the lantern (shared room state).
        - alice walks east to the library and takes the old book.
        - bob is back in the foyer and must NOT receive any broadcast for
          alice's library-side actions.
        """
        alice, _ = server.connect("alice")
        bob, _ = server.connect("bob")
        # Drain alice's "bob arrives" broadcast so the buffer starts clean.
        alice.drain(settle=0.05)

        # alice takes the lantern.
        resp = alice.cmd("take lantern")
        assert "Taken." in lines(resp)

        # bob's socket received the pickup broadcast.
        bc = bob.drain(settle=0.15)
        assert "alice picks up the brass lantern." in bc, \
            f"bob should see alice's pickup broadcast, got: {bc!r}"

        # And bob's view of the foyer no longer lists the lantern: room
        # state is shared, not per-player.
        resp = bob.cmd("look")
        you_see = next((l for l in lines(resp) if l.startswith("You see:")), "")
        assert "brass lantern" not in you_see, \
            f"Lantern is in alice's inventory now; bob should not see it: {resp!r}"
        # The other foyer object (rusted key) is still there.
        assert "rusted key" in you_see, \
            f"Rusted key should still be in bob's foyer view: {resp!r}"

        # alice walks east to the library, alone.
        resp = alice.cmd("east")
        assert "Library" in lines(resp)[0]

        # bob receives the departure broadcast for that move...
        bc = bob.drain(settle=0.15)
        assert "alice leaves to the east." in bc, \
            f"bob should see alice's departure broadcast, got: {bc!r}"

        # ...but no further broadcasts after that, even when alice does
        # something visible in the library.
        assert "Taken." in lines(alice.cmd("take book"))

        # bob's socket: nothing more should arrive — alice is in a
        # different room. drain's settle interval is generous enough to
        # catch a leaked broadcast if one fired.
        leaked = bob.drain(settle=0.2)
        assert leaked == "", \
            f"bob (in foyer) must not receive broadcasts for alice's library actions, got: {leaked!r}"
