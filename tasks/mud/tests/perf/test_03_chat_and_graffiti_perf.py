"""Stage 3 performance benchmark: concurrent clients + NPC ticks +
persistence under load.

Stage 3 layers three new sources of work onto the Stage 2 server:
  - chat broadcasts (`say`)
  - writes that fsync to `graffiti.json` (`write`, `describe me`)
  - NPC ticks driven by a wallclock heartbeat

This perf test stresses all three at once. N concurrent clients in the
library (where the ghost and adventurer NPCs are also active) cycle
through say / write / describe / look while the NPC heartbeat fires
every 0.3 s. Aggregate ops/sec is reported.

Lazy implementations show up here in several ways:
  - serializing all sessions through a single global lock caps throughput
  - rewriting all of graffiti.json synchronously per write becomes the
    dominant cost as the file grows (each cycle adds an inscription)
  - blocking sendall to one slow recipient stalls broadcasts to others
  - tick scheduling that doesn't yield to commands stalls under load

No hard asserts — perf tests must produce a measurement even on a partly
broken implementation. Per-command exceptions are swallowed.
"""
import os
import threading
import time

import pytest

from conftest import MUDServer, MUDClient, _free_port, lines, DEFAULT_SERVER_CMD, _clean_graffiti


WORKLOAD_CYCLE = [
    'say "hello"',
    'describe me "a weary traveller"',
    'write "x" on plaque',
    "look",
]


def _client_worker(client, cycles, errors):
    try:
        for _ in range(cycles):
            for cmd in WORKLOAD_CYCLE:
                # Drain stale broadcasts (NPCs, other players' say/write)
                # so they're not folded into our response.
                client.drain(settle=0.0)
                client.cmd(cmd, timeout=10.0)
    except Exception as e:  # pragma: no cover
        errors.append(repr(e))


class TestStage3Throughput:
    def test_concurrent_chat_write_describe_with_npc_ticks(self):
        """N clients in the library; NPCs ticking at 0.3 s; each client
        cycles through say + describe + write + look. Reports aggregate
        ops/sec.
        """
        cmd = os.environ.get("SERVER_CMD", DEFAULT_SERVER_CMD)
        _clean_graffiti()
        port = _free_port()
        # Fast tick — NPCs are firing constantly during the test, adding
        # to the broadcast load each client receives.
        server = MUDServer(cmd, port, extra_args="--tick-seconds 0.3")
        clients = []
        try:
            n_clients = 8
            cycles = 30  # 4 cmds × 30 cycles × 8 clients = 960 commands
            for i in range(n_clients):
                c = MUDClient("127.0.0.1", port)
                c.login(f"user{i}")
                # Walk to the library where the NPCs are.
                c.cmd("east")
                clients.append(c)
            # Drain accumulated NPC broadcasts on each client.
            for c in clients:
                c.drain(settle=0.1)

            errors = []
            threads = [
                threading.Thread(target=_client_worker, args=(c, cycles, errors), daemon=True)
                for c in clients
            ]

            start = time.perf_counter()
            for t in threads:
                t.start()
            for t in threads:
                t.join(timeout=120.0)
            elapsed = time.perf_counter() - start

            total_cmds = n_clients * cycles * len(WORKLOAD_CYCLE)
            ops_per_second = (total_cmds / elapsed) if elapsed > 0 else 0.0

            print(
                f'{{"bench_metric": "ops_per_second", '
                f'"test": "test_concurrent_chat_write_describe_with_npc_ticks", '
                f'"value": {ops_per_second:.2f}, '
                f'"iterations": {total_cmds}, '
                f'"duration_seconds": {elapsed:.6f}, '
                f'"clients": {n_clients}, '
                f'"cycles_per_client": {cycles}, '
                f'"errors": {len(errors)}}}'
            )
        finally:
            for c in clients:
                try:
                    c.close()
                except Exception:
                    pass
            server.close()
            _clean_graffiti()
