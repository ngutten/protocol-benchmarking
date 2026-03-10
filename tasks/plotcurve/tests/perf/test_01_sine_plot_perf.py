"""Performance benchmarks for Stage 1: Sine wave plot.

Holdout — never provided to the LLM.
Measures per-invocation latency for the default sine plot at various resolutions.
"""
import time
import os


class TestSinePlotPerf:
    def test_default_plot_latency(self, engine):
        """Baseline latency: default sine plot with default settings."""
        # Warm-up
        engine.run_ok()
        start = time.perf_counter()
        for _ in range(10):
            engine.run_ok()
        elapsed = time.perf_counter() - start
        print(f'{{"bench_metric": "ops_per_second", "test": "test_default_plot_latency", "value": {10 / elapsed:.2f}, "iterations": 10, "duration_seconds": {elapsed:.6f}}}')

    def test_high_resolution_plot(self, engine):
        """Latency with 2000 sample points."""
        start = time.perf_counter()
        for _ in range(10):
            engine.run_ok({"n_points": 2000})
        elapsed = time.perf_counter() - start
        print(f'{{"bench_metric": "ops_per_second", "test": "test_high_resolution_plot", "value": {10 / elapsed:.2f}, "iterations": 10, "duration_seconds": {elapsed:.6f}}}')

    def test_wide_range_plot(self, engine):
        """Latency with a wide x range (-1000 to 1000)."""
        start = time.perf_counter()
        for _ in range(10):
            engine.run_ok({"x_min": -1000, "x_max": 1000, "n_points": 1000})
        elapsed = time.perf_counter() - start
        print(f'{{"bench_metric": "ops_per_second", "test": "test_wide_range_plot", "value": {10 / elapsed:.2f}, "iterations": 10, "duration_seconds": {elapsed:.6f}}}')
