"""Performance benchmarks for Stage 1: Conway's Game of Life."""
import time
import pytest


class TestConwayStepThroughput:
    """Measure step throughput at various grid sizes."""

    def test_256x256_100_steps(self, sim_factory):
        """100 steps on a 256x256 grid with random-ish initial state."""
        s = sim_factory(width=256, height=256)
        # Seed with a diagonal band of cells
        for i in range(256):
            s.set_cell(i, i, 1)
            s.set_cell(i, (i + 1) % 256, 1)

        start = time.perf_counter()
        s.step(100)
        elapsed = time.perf_counter() - start

        # Verify the simulation actually ran
        assert s.get_step_count() == 100
        assert elapsed > 0

        print(f'{{"bench_metric": "step_time_seconds", "test": "test_256x256_100_steps", '
              f'"value": {elapsed:.6f}, "grid": "256x256", "iterations": 100, '
              f'"duration_seconds": {elapsed:.6f}}}')

    def test_512x512_25_steps(self, sim_factory):
        """25 steps on a 512x512 grid."""
        s = sim_factory(width=512, height=512)
        for i in range(512):
            s.set_cell(i, i, 1)
            s.set_cell(i, (i + 1) % 512, 1)

        start = time.perf_counter()
        s.step(25)
        elapsed = time.perf_counter() - start

        assert s.get_step_count() == 25
        assert elapsed > 0

        print(f'{{"bench_metric": "step_time_seconds", "test": "test_512x512_25_steps", '
              f'"value": {elapsed:.6f}, "grid": "512x512", "iterations": 25, '
              f'"duration_seconds": {elapsed:.6f}}}')

    def test_16x16_10000_steps(self, sim_factory):
        """10000 steps on a small 16x16 grid (function call overhead)."""
        s = sim_factory(width=16, height=16)
        # Seed with a glider
        for x, y in [(1, 0), (2, 1), (0, 2), (1, 2), (2, 2)]:
            s.set_cell(x, y, 1)

        start = time.perf_counter()
        s.step(10000)
        elapsed = time.perf_counter() - start

        assert s.get_step_count() == 10000
        # Glider on 16x16 periodic should still be alive
        assert s.count_alive() == 5

        print(f'{{"bench_metric": "step_time_seconds", "test": "test_16x16_10000_steps", '
              f'"value": {elapsed:.6f}, "grid": "16x16", "iterations": 10000, '
              f'"duration_seconds": {elapsed:.6f}}}')


class TestCountAliveThroughput:
    """Measure count_alive performance."""

    def test_count_alive_256x256(self, sim_factory):
        """1000 count_alive calls on a 256x256 grid."""
        s = sim_factory(width=256, height=256)
        # Seed some cells
        for i in range(0, 256, 2):
            for j in range(0, 256, 2):
                s.set_cell(i, j, 1)

        n_calls = 1000
        start = time.perf_counter()
        result = 0
        for _ in range(n_calls):
            result = s.count_alive()
        elapsed = time.perf_counter() - start

        # Verify count_alive actually computed something
        assert result > 0

        print(f'{{"bench_metric": "ops_per_second", "test": "test_count_alive_256x256", '
              f'"value": {n_calls / elapsed:.2f}, "iterations": {n_calls}, '
              f'"duration_seconds": {elapsed:.6f}}}')
