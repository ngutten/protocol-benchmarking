"""Stage 1 performance benchmark: command throughput on the shipped world.

Measures end-to-end ops/sec over a representative mix of valid commands.
This primarily stresses per-command overhead — parsing, object resolution,
room output, and stdio round-trip — rather than any algorithmic hotspot,
since the shipped world is small. Lazy implementations that re-parse
`assets/world.json` on every command, deep-copy world state per command,
or use unbuffered/unflushed stdio will show up as noticeably lower
throughput here.

Asserts are avoided so a buggy implementation still produces a measurement.
"""
import time


# Workload: 1000 commands covering every Stage 1 verb, plus both lit and
# dark rooms (so darkness evaluation runs on most look calls).
# Each "tick" is a 10-command loop; 100 ticks = 1000 commands.
WORKLOAD_TICK = [
    "look",
    "i",
    "take lantern",
    "use lantern",
    "east",
    "look",
    "look book",
    "use book",
    "west",
    "drop lantern",
]


def _run_ticks(session, n_ticks):
    """Run the workload, tolerating mid-stream errors. Returns (elapsed, commands_issued)."""
    commands_issued = 0
    start = time.perf_counter()
    try:
        for _ in range(n_ticks):
            for cmd in WORKLOAD_TICK:
                session.cmd(cmd, timeout=5.0)
                commands_issued += 1
    except Exception:
        pass
    elapsed = time.perf_counter() - start
    return elapsed, commands_issued


class TestStage1Throughput:
    def test_command_throughput(self, session):
        """Throughput across a mixed-verb workload.

        The workload alternates between the foyer (lit, two starting
        objects) and the library (lit, plaque + book) and exercises
        look, inventory, take, drop, use (toggle), and movement.
        """
        n_ticks = 100  # 1000 commands total
        elapsed, issued = _run_ticks(session, n_ticks)
        ops_per_second = (issued / elapsed) if elapsed > 0 else 0.0
        print(
            f'{{"bench_metric": "ops_per_second", '
            f'"test": "test_command_throughput", '
            f'"value": {ops_per_second:.2f}, '
            f'"iterations": {issued}, '
            f'"duration_seconds": {elapsed:.6f}}}'
        )
