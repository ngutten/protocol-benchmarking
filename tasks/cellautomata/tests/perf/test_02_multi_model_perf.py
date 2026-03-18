"""Performance benchmarks for Stage 2: Falling Sand, Langton's Ant, multi-model."""
import time
import pytest

class TestLangtonThroughput:
    """Measure Langton's ant stepping performance."""

    def test_langton_10k_steps_128x128(self, sim_factory):
        """10,000 steps of Langton's ant on 128x128."""
        s = sim_factory(model="langton", width=128, height=128)

        start = time.perf_counter()
        s.step(10000)
        elapsed = time.perf_counter() - start

        assert s.get_step_count() == 10000
        # Ant should have moved from center
        ant = s.get_ant()
        assert ant["x"] != 64 or ant["y"] != 64

        print(f'{{"bench_metric": "step_time_seconds", "test": "test_langton_10k_steps_128x128", '
              f'"value": {elapsed:.6f}, "grid": "128x128", "iterations": 10000, '
              f'"duration_seconds": {elapsed:.6f}}}')

    def test_langton_5k_steps_256x256(self, sim_factory):
        """5,000 steps of Langton's ant on 256x256."""
        s = sim_factory(model="langton", width=256, height=256)

        start = time.perf_counter()
        s.step(5000)
        elapsed = time.perf_counter() - start

        assert s.get_step_count() == 5000
        assert s.count_alive() > 0

        print(f'{{"bench_metric": "step_time_seconds", "test": "test_langton_5k_steps_256x256", '
              f'"value": {elapsed:.6f}, "grid": "256x256", "iterations": 5000, '
              f'"duration_seconds": {elapsed:.6f}}}')


class TestMultiModelComparison:
    """Benchmark all three models at the same grid size."""

    def test_all_models_128x128(self, sim_factory):
        """Run 100 steps for each model on 128x128 and report times."""
        results = {}

        # Conway
        s = sim_factory(model="conway", width=128, height=128)
        for i in range(128):
            s.set_cell(i, i, 1)
        start = time.perf_counter()
        s.step(100)
        results["conway"] = time.perf_counter() - start
        assert s.get_step_count() == 100

        # Falling Sand (100 sweeps)
        s = sim_factory(model="sandpile", width=128, height=128)
        s.set_cell(64, 0, 100)
        start = time.perf_counter()
        s.step(100)
        results["sandpile"] = time.perf_counter() - start
        assert s.get_step_count() == 100

        # Langton
        s = sim_factory(model="langton", width=128, height=128)
        start = time.perf_counter()
        s.step(100)
        results["langton"] = time.perf_counter() - start
        assert s.get_step_count() == 100

        for model, elapsed in results.items():
            print(f'{{"bench_metric": "step_time_seconds", "test": "test_all_models_128x128", '
                  f'"model": "{model}", "value": {elapsed:.6f}, "grid": "128x128", "iterations": 100, '
                  f'"duration_seconds": {elapsed:.6f}}}')
