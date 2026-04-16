"""Stage 2 holdout tests: edge cases, ambiguity probes, and security
adjacent scenarios. Specifically NOT redundant with the training tests.
"""
import socket as _socket
import time

import pytest

from conftest import lines


def _also_here(resp):
    return next((l for l in lines(resp) if l.startswith("Also here:")), "")


class TestCaseInsensitiveSort:
    def test_who_sorts_case_insensitively(self, server):
        """`who` orders names case-insensitively, NOT by ASCII codepoint.

        ASCII sort would place all uppercase names before all lowercase
        ones, putting "Bob" and "Carol" before "alice". The spec calls for
        case-insensitive alphabetical, so the order must be:
            alice, Bob, Carol
        """
        # Login order is irrelevant — the sort is purely by name.
        sa, _ = server.connect("Carol")
        sb, _ = server.connect("alice")
        sc, _ = server.connect("Bob")
        # Drain arrival broadcasts before asking who.
        sa.drain(settle=0.05); sb.drain(settle=0.05); sc.drain(settle=0.05)

        resp = sa.cmd("who")
        names = [l.strip() for l in lines(resp)]
        assert names == ["alice", "Bob", "Carol"], \
            f"who must sort case-insensitively, got: {names}"

    def test_also_here_sorts_case_insensitively_and_agrees_with_who(self, server):
        """The `Also here:` line uses the same case-insensitive ordering
        as `who`. They must agree — an implementation that uses ASCII
        sort in one place and case-folded sort in the other would be
        internally inconsistent.
        """
        sa, _ = server.connect("Charlie")
        sb, _ = server.connect("Bob")
        sc, _ = server.connect("alice")
        sd, _ = server.connect("alice2")
        # All four are now in the foyer. Drain arrival noise on sd, who
        # is the most recent login.
        sd.drain(settle=0.05)

        # sd's `look` should list the other three on Also here.
        resp = sd.cmd("look")
        line = _also_here(resp)
        # alice2 is the calling player and is excluded.
        assert "alice2" not in line, \
            f"Calling player must be excluded from Also here: {line!r}"
        # Order: alice, Bob, Charlie (case-insensitive).
        assert line == "Also here: alice, Bob, Charlie", \
            f"Also here must be case-insensitive sorted, got: {line!r}"

        # And `who` returns the same names in the same order, plus self.
        resp = sd.cmd("who")
        names = [l.strip() for l in lines(resp)]
        assert names == ["alice", "alice2", "Bob", "Charlie"], \
            f"who must agree with Also here ordering rule, got: {names}"


class TestAbruptDisconnect:
    def test_hard_disconnect_drops_inventory_in_room(self, server):
        """If a client closes its socket without sending `quit`, the spec
        requires the server to:
        - broadcast `<name> disconnects.` to the room they were in
        - drop their entire inventory on the floor of that room

        Tests the abrupt-disconnect cleanup path, which is easy to miss
        in implementations that only handle the clean `quit` case.
        """
        alice, _ = server.connect("alice")
        bob, _ = server.connect("bob")
        bob.drain(settle=0.05)  # consume alice's foyer-arrival noise

        # Alice picks up both foyer items.
        assert "Taken." in lines(alice.cmd("take lantern"))
        assert "Taken." in lines(alice.cmd("take rusted key"))

        # Bob should see both pickup broadcasts.
        bc = bob.drain(settle=0.15)
        assert "alice picks up the brass lantern." in bc, \
            f"Expected lantern pickup broadcast, got: {bc!r}"
        assert "alice picks up the rusted key." in bc, \
            f"Expected key pickup broadcast, got: {bc!r}"

        # Sanity: both items now absent from the foyer's view.
        resp = bob.cmd("look")
        you_see = next((l for l in lines(resp) if l.startswith("You see:")), "")
        assert "brass lantern" not in you_see and "rusted key" not in you_see, \
            f"Foyer should be empty of those objects, got: {resp!r}"

        # Hard disconnect — close the socket without sending quit.
        alice.close()

        # Bob should receive the disconnect broadcast.
        bc = bob.drain(settle=0.3)
        assert "alice disconnects." in bc, \
            f"Bob should see alice's disconnect broadcast, got: {bc!r}"

        # And alice's inventory should now be in the foyer's object list.
        # Acquisition order was lantern, key.
        resp = bob.cmd("look")
        you_see = next((l for l in lines(resp) if l.startswith("You see:")), "")
        assert "brass lantern" in you_see, \
            f"Lantern should reappear in foyer after alice's disconnect: {resp!r}"
        assert "rusted key" in you_see, \
            f"Rusted key should reappear in foyer after alice's disconnect: {resp!r}"

        # Now bob can pick them up — confirms the items are real objects
        # in the room, not just listed cosmetically.
        assert "Taken." in lines(bob.cmd("take lantern"))
        assert "Taken." in lines(bob.cmd("take key"))

    def test_hard_disconnect_drops_in_correct_room(self, server):
        """The dropped inventory ends up in the room the player was IN
        when they disconnected, not the starting room. Alice walks east
        to the library, takes the book, then disconnects — the book
        should appear in the library, not the foyer.
        """
        alice, _ = server.connect("alice")
        bob, _ = server.connect("bob")
        bob.drain(settle=0.05)

        # Alice walks east, takes the book.
        alice.cmd("east")
        bob.drain(settle=0.05)  # alice leaves broadcast on bob
        assert "Taken." in lines(alice.cmd("take book"))

        # Sanity: bob is in foyer, not library — he sees no take broadcast.
        leaked = bob.drain(settle=0.1)
        assert leaked == "", \
            f"Bob (in foyer) should not see alice's library actions: {leaked!r}"

        # Alice disconnects.
        alice.close()
        bob.drain(settle=0.2)  # bob doesn't see this either; alice was elsewhere

        # bob walks to the library and looks: book should be there.
        resp = bob.cmd("east")
        you_see = next((l for l in lines(resp) if l.startswith("You see:")), "")
        assert "old book" in you_see, \
            f"Book should be in library after alice disconnected there: {resp!r}"


class TestLoginEdgeCases:
    def test_pre_login_commands_rejected(self, server):
        """Before a successful login, the server accepts only `login <name>`.
        Anything else must produce 'Please log in first.' and a prompt,
        leaving the connection open for another login attempt.
        """
        c = server.connect()  # no auto-login

        # Various non-login commands are all rejected.
        for cmd in ("look", "who", "inventory", "go east", "quit"):
            resp = c.cmd(cmd)
            assert "Please log in first." in lines(resp), \
                f"{cmd!r} pre-login should be rejected, got: {resp!r}"

        # The connection is still alive — we can now log in.
        resp = c.login("alice")
        assert "Welcome, alice." in lines(resp), \
            f"Should be able to log in after rejected commands, got: {resp!r}"
        # And subsequent commands now work.
        resp = c.cmd("look")
        assert "Foyer" in lines(resp)[0]

    def test_duplicate_name_rejected_then_recoverable(self, server):
        """A second login with a name already in use is rejected with
        'Name already in use.'; the connection stays open for another
        login attempt with a different name.
        """
        alice, _ = server.connect("alice")

        # New connection tries to also be alice.
        impostor = server.connect()
        resp = impostor.login("alice")
        assert "Name already in use." in lines(resp), \
            f"Duplicate name should be rejected, got: {resp!r}"

        # Connection still alive — original alice should NOT see any
        # arrival broadcast for the impostor (they never logged in).
        leaked = alice.drain(settle=0.1)
        assert "arrives" not in leaked, \
            f"Failed login must not produce arrival broadcast on alice's socket: {leaked!r}"

        # Impostor retries with a different name and succeeds.
        resp = impostor.login("bob")
        assert "Welcome, bob." in lines(resp), \
            f"Recovery login should succeed, got: {resp!r}"

        # NOW alice should see "bob arrives."
        bc = alice.drain(settle=0.15)
        assert "bob arrives." in bc, \
            f"alice should see bob's arrival broadcast after successful login: {bc!r}"

    def test_invalid_name_formats_rejected(self, server):
        """Names that are empty, contain whitespace, or exceed 32 chars
        are rejected with 'Invalid name.' Connection stays open.
        """
        c = server.connect()

        # Empty name (`login ` with nothing after).
        resp = c.cmd("login")
        assert "Invalid name." in lines(resp), \
            f"`login` with no name should be Invalid name., got: {resp!r}"

        # Name with whitespace.
        resp = c.cmd("login alice bob")
        assert "Invalid name." in lines(resp), \
            f"Multi-word name should be Invalid name., got: {resp!r}"

        # Over-length name (33 chars).
        long_name = "a" * 33
        resp = c.cmd(f"login {long_name}")
        assert "Invalid name." in lines(resp), \
            f"33-char name should be Invalid name., got: {resp!r}"

        # And after all those rejections, a valid login still works.
        resp = c.login("alice")
        assert "Welcome, alice." in lines(resp)


class TestSlowClientIsolation:
    def test_slow_client_does_not_block_other_sessions(self, server):
        """A connected client that stops reading from its socket must not
        block other sessions' commands.

        Stage 2 spec: 'commands from different connections may interleave
        freely; the server is responsible for keeping shared state ...
        internally consistent under concurrent access' and 'MUST handle
        at least 32 simultaneous connected clients without blocking one
        client's input on another client's work.'

        The natural way to violate this is to hold a global lock while
        calling `sendall()` to broadcast: a client whose receive buffer
        is full forces the server's send to block, which (with the lock
        held) freezes every other session.

        Setup: bob is a normal client. alice is a raw socket that NEVER
        reads anything, with a tiny SO_RCVBUF so the kernel send buffer
        fills quickly. Bob then performs a stream of broadcast-triggering
        actions and we assert his commands keep responding promptly.
        """
        # bob is a normal client
        bob, _ = server.connect("bob")

        # alice: raw socket, smallest receive buffer the kernel will give
        # us, and never reads. We need to fill BOTH alice's receive buffer
        # AND the server-side send buffer before sendall blocks. On Linux
        # the server-side send buffer can be ~200 KB, so a healthy run
        # needs to push that much data before the (potentially) buggy
        # path triggers — that's what the iteration count is sized for.
        alice = _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM)
        alice.setsockopt(_socket.SOL_SOCKET, _socket.SO_RCVBUF, 1)
        alice.connect(("127.0.0.1", server.port))
        alice.sendall(b"login alice\n")
        # Deliberately do NOT read alice's welcome — we want her receive
        # buffer to start filling immediately.

        # bob receives alice's arrival broadcast; drain it.
        bob.drain(settle=0.15)

        # Each take/drop iteration pushes ~64 bytes of broadcast onto
        # alice's socket. Linux's TCP autotuning lets each connection's
        # send buffer grow to several MB, and empirically the actual
        # blocking threshold to a stuck loopback client is around 800 KB
        # to 1 MB. So we run ~20 000 iterations (~1.3 MB of broadcast
        # data) to comfortably cross that threshold.
        #
        # We track per-command latency. On a healthy server every command
        # completes within milliseconds. On a buggy server (lock held
        # during sendall), an individual command will block for seconds
        # once the buffer fills.
        iterations = 20000
        max_latency = 0.0
        max_at = -1
        last_i = -1
        try:
            for i in range(iterations):
                last_i = i
                t0 = time.perf_counter()
                resp = bob.cmd("take lantern", timeout=2.0)
                resp = bob.cmd("drop lantern", timeout=2.0)
                dt = time.perf_counter() - t0
                if dt > max_latency:
                    max_latency = dt
                    max_at = i
        except TimeoutError:
            pytest.fail(
                f"bob's commands started timing out at iteration {last_i} "
                f"(after max latency {max_latency:.3f}s seen at iteration {max_at}). "
                "A stuck client must not block other sessions — the server "
                "is likely holding a lock while blocked in sendall."
            )
        finally:
            try:
                alice.close()
            except Exception:
                pass

        # Drain any disconnect broadcast triggered by alice.close() before
        # asserting bob's next command works.
        bob.drain(settle=0.2)

        assert max_latency < 1.0, (
            f"Some bob command took {max_latency:.3f}s (at iteration {max_at}). "
            "A stuck client (alice) is slowing every other session — the "
            "server is likely holding a global lock during sendall to a "
            "blocked client."
        )

        # And after all that, bob's session is still healthy.
        resp = bob.cmd("look", timeout=2.0)
        assert "Foyer" in lines(resp)[0]


class TestLookAtPlayer:
    def test_look_at_other_player_and_self(self, server):
        """`look <name>` resolves to a player when no object matches.

        Spec: target resolution at Stage 2 is inventory → room objects →
        players in current room (including self). The match prints
        `<name> is another adventurer.`. Self is matchable.
        """
        alice, _ = server.connect("alice")
        bob, _ = server.connect("bob")
        alice.drain(settle=0.05)

        # alice looks at bob.
        resp = alice.cmd("look bob")
        assert "bob is another adventurer." in lines(resp), \
            f"Look at other player should return generic line, got: {resp!r}"

        # alice looks at herself.
        resp = alice.cmd("look alice")
        assert "alice is another adventurer." in lines(resp), \
            f"Look at self should return the same generic line, got: {resp!r}"

        # A name that isn't a player and isn't an object: no such target.
        resp = alice.cmd("look carol")
        assert "There is no carol here." in lines(resp), \
            f"Non-existent target should give no-such-target, got: {resp!r}"

    def test_player_not_in_room_is_unreachable(self, server):
        """`look <name>` only matches players in the SAME room. A player
        elsewhere doesn't resolve, even though they are logged in.
        """
        alice, _ = server.connect("alice")
        bob, _ = server.connect("bob")
        alice.drain(settle=0.05)

        # bob walks east to the library; alice stays in foyer.
        bob.cmd("east")
        alice.drain(settle=0.1)  # consume bob's leave broadcast

        # alice looks at bob — bob is not in alice's room.
        resp = alice.cmd("look bob")
        assert "There is no bob here." in lines(resp), \
            f"bob is in a different room; look should not match, got: {resp!r}"

        # bob can still look at himself, where he is.
        resp = bob.cmd("look bob")
        assert "bob is another adventurer." in lines(resp), \
            f"bob should be able to look at himself in the library, got: {resp!r}"

    def test_object_match_takes_priority_over_player_name(self, server):
        """If a player and an object share a name, target resolution must
        prefer the object (objects come earlier in the resolution order).

        We don't have such a clash in the canonical world, so we contrive
        one: a player named 'lantern' in the foyer. `look lantern` should
        match the brass lantern (alias 'lantern'), not the player.
        """
        alice, _ = server.connect("alice")
        # Login a second player with the special name.
        lan, resp = server.connect("lantern")
        # Skip if the server rejected the name for any reason — the
        # object-shadowing assertion only matters if we got the player in.
        if "Welcome, lantern." not in lines(resp):
            pytest.skip(f"Server did not accept name 'lantern': {resp!r}")
        alice.drain(settle=0.05)

        resp = alice.cmd("look lantern")
        # Brass lantern's description mentions "brass" — generic player
        # line does not. So the shadowing object must win.
        assert "brass" in " ".join(lines(resp)).lower(), \
            f"Object 'brass lantern' should shadow player named 'lantern', got: {resp!r}"
        assert "another adventurer" not in " ".join(lines(resp)).lower(), \
            f"Player line should not appear when object matches, got: {resp!r}"
