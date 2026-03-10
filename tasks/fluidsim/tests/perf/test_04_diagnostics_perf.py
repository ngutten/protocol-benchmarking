"""Performance benchmarks for Stage 4: Diagnostics computation."""
import time
import pytest


class TestDiagnosticsComputePerf:
    def test_diagnostics_compute_32x32(self, engine):
        """Diagnostics computation time on 32x32 cavity."""
        engine.create(nx=32, ny=32, lx=1.0, ly=1.0, viscosity=0.01)
        engine.set_boundary("top", "velocity", value=[1.0, 0.0])
        engine.set_boundary("bottom", "no_slip")
        engine.set_boundary("left", "no_slip")
        engine.set_boundary("right", "no_slip")
        engine.solve_steady(tolerance=1e-5)

        n_queries = 100
        start = time.perf_counter()
        for _ in range(n_queries):
            engine.get_diagnostics()
        elapsed = time.perf_counter() - start

        print(f'{{"bench_metric": "ops_per_second", "test": "test_diagnostics_compute_32x32", "value": {n_queries / elapsed:.2f}, "iterations": {n_queries}, "duration_seconds": {elapsed:.6f}}}')

    def test_diagnostics_with_obstacle_64x32(self, engine):
        """Diagnostics with obstacle on 64x32 grid."""
        engine.create(nx=64, ny=32, lx=4.0, ly=1.0, viscosity=0.05)
        engine.set_boundary("left", "inflow", profile="uniform", velocity=[1.0, 0.0])
        engine.set_boundary("right", "outflow")
        engine.set_boundary("top", "no_slip")
        engine.set_boundary("bottom", "no_slip")
        engine.add_obstacle("circle", center=[1.0, 0.5], radius=0.1)
        engine.solve_steady(tolerance=1e-4, max_iterations=100000)

        n_queries = 50
        start = time.perf_counter()
        for _ in range(n_queries):
            engine.get_diagnostics()
        elapsed = time.perf_counter() - start

        print(f'{{"bench_metric": "ops_per_second", "test": "test_diagnostics_with_obstacle_64x32", "value": {n_queries / elapsed:.2f}, "iterations": {n_queries}, "duration_seconds": {elapsed:.6f}}}')


class TestHistoryPerf:
    def test_stepping_with_diagnostics_32x32(self, engine):
        """Time stepping with diagnostic recording on 32x32."""
        engine.create(nx=32, ny=32, lx=1.0, ly=1.0, viscosity=0.01)
        engine.set_boundary("top", "velocity", value=[1.0, 0.0])
        engine.set_boundary("bottom", "no_slip")
        engine.set_boundary("left", "no_slip")
        engine.set_boundary("right", "no_slip")

        n_steps = 100
        start = time.perf_counter()
        engine.step(dt=0.001, steps=n_steps)
        elapsed = time.perf_counter() - start

        # Check that history was recorded
        hist = engine.get_diagnostic_history("kinetic_energy")
        assert len(hist["values"]) > 0

        print(f'{{"bench_metric": "steps_per_second", "test": "test_stepping_with_diagnostics_32x32", "value": {n_steps / elapsed:.2f}, "iterations": {n_steps}, "duration_seconds": {elapsed:.6f}}}')
