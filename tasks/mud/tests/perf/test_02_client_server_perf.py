"""Stage 2 performance benchmark: concurrent multi-client throughput.

Stage 2's headline new capability is concurrency — multiple players
connecting to one server. The natural perf scenario is many clients in
the same room, each issuing commands; every action broadcasts to every
other client. This stresses both the per-command processing path and
the broadcast fanout pipeline.

Lazy implementations that serialize sessions (one global lock held
during all of dispatch + broadcast + sendall) flatline at single-thread
speeds regardless of client count. A well-designed server scales close
to the kernel's IPC limits.

No hard asserts — perf tests must produce a measurement even on partly
broken implementations. We do swallow per-command errors so a single
flaky session doesn't hide the aggregate throughput.
"""
import threading
import time

import pytest

from conftest import MUDClient, MUDServer, _free_port, lines, DEFAULT_SERVER_CMD


# Workload: each client issues this 4-command cycle. Take and drop fire
# broadcasts; look and inventory don't. Mixing them keeps the broadcast
# fanout heavy without making every command broadcast.
WORKLOAD_CYCLE = ["take lantern", "drop lantern", "look", "inventory"]


def _client_worker(client, cycles, errors):
    """Run the workload on one client; record any exceptions."""
    try:
        for _ in range(cycles):
            for cmd in WORKLOAD_CYCLE:
                # Drain any backlog of broadcasts before each command so
                # `cmd()` doesn't accidentally consume them as our own
                # response. (drain is non-blocking with settle=0.)
                client.drain(settle=0.0)
                client.cmd(cmd, timeout=10.0)
    except Exception as e:  # pragma: no cover — defensive for perf tests
        errors.append(repr(e))


class TestStage2Throughput:
    def test_concurrent_clients_same_room(self):
        """N clients all in the foyer, each running a workload cycle in
        its own thread. Reports aggregate ops/sec across all clients.
        """
        import os
        cmd = os.environ.get("SERVER_CMD", DEFAULT_SERVER_CMD)
        port = _free_port()
        server = MUDServer(cmd, port)
        clients = []
        try:
            n_clients = 8
            cycles = 80  # 4 commands × 80 cycles × 8 clients = 2560 cmds total
            # Connect everyone first; only then start measuring.
            for i in range(n_clients):
                c = MUDClient("127.0.0.1", port)
                c.login(f"user{i}")
                clients.append(c)
            # Drain arrival broadcasts on each client.
            for c in clients:
                c.drain(settle=0.05)

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
                f'"test": "test_concurrent_clients_same_room", '
                f'"value": {ops_per_second:.2f}, '
                f'"iterations": {total_cmds}, '
                f'"duration_seconds": {elapsed:.6f}, '
                f'"clients": {n_clients}, '
                f'"errors": {len(errors)}}}'
            )
        finally:
            for c in clients:
                try:
                    c.close()
                except Exception:
                    pass
            server.close()
