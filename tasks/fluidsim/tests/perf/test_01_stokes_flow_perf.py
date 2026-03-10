"""Performance benchmarks for Stage 1: Stokes flow solver."""
import time
import pytest


class TestStokesSolveThroughput:
    def test_stokes_32x32(self, engine):
        """Stokes solve time on 32x32 grid."""
        engine.create(nx=32, ny=32, lx=1.0, ly=1.0, viscosity=0.1, force=[1.0, 0.0])
        engine.set_boundary("top", "no_slip")
        engine.set_boundary("bottom", "no_slip")
        engine.set_boundary("left", "velocity", value=[0.0, 0.0])
        engine.set_boundary("right", "velocity", value=[0.0, 0.0])

        start = time.perf_counter()
        resp = engine.solve_steady(tolerance=1e-6, max_iterations=50000)
        elapsed = time.perf_counter() - start

        assert resp["converged"] is True
        print(f'{{"bench_metric": "solve_time_seconds", "test": "test_stokes_32x32", "value": {elapsed:.6f}, "grid": "32x32", "iterations": {resp["iterations"]}}}')

    def test_stokes_64x64(self, engine):
        """Stokes solve time on 64x64 grid."""
        engine.create(nx=64, ny=64, lx=1.0, ly=1.0, viscosity=0.1, force=[1.0, 0.0])
        engine.set_boundary("top", "no_slip")
        engine.set_boundary("bottom", "no_slip")
        engine.set_boundary("left", "velocity", value=[0.0, 0.0])
        engine.set_boundary("right", "velocity", value=[0.0, 0.0])

        start = time.perf_counter()
        resp = engine.solve_steady(tolerance=1e-6, max_iterations=100000)
        elapsed = time.perf_counter() - start

        assert resp["converged"] is True
        print(f'{{"bench_metric": "solve_time_seconds", "test": "test_stokes_64x64", "value": {elapsed:.6f}, "grid": "64x64", "iterations": {resp["iterations"]}}}')


class TestFieldQueryThroughput:
    def test_field_query_repeated(self, engine):
        """Repeated field queries after solve."""
        engine.create(nx=32, ny=32, lx=1.0, ly=1.0, viscosity=0.1)
        engine.set_boundary("top", "velocity", value=[1.0, 0.0])
        engine.set_boundary("bottom", "no_slip")
        engine.set_boundary("left", "no_slip")
        engine.set_boundary("right", "no_slip")
        engine.solve_steady(tolerance=1e-5)

        n_queries = 50
        start = time.perf_counter()
        for _ in range(n_queries):
            engine.get_field("velocity_x")
        elapsed = time.perf_counter() - start

        print(f'{{"bench_metric": "ops_per_second", "test": "test_field_query_repeated", "value": {n_queries / elapsed:.2f}, "iterations": {n_queries}, "duration_seconds": {elapsed:.6f}}}')

    def test_point_query_repeated(self, engine):
        """Repeated point value queries."""
        engine.create(nx=32, ny=32, lx=1.0, ly=1.0, viscosity=0.1)
        engine.set_boundary("top", "velocity", value=[1.0, 0.0])
        engine.set_boundary("bottom", "no_slip")
        engine.set_boundary("left", "no_slip")
        engine.set_boundary("right", "no_slip")
        engine.solve_steady(tolerance=1e-5)

        n_queries = 200
        start = time.perf_counter()
        for i in range(n_queries):
            x = 0.1 + 0.8 * (i % 10) / 10.0
            y = 0.1 + 0.8 * (i // 10 % 10) / 10.0
            engine.get_value("velocity_x", [x, y])
        elapsed = time.perf_counter() - start

        print(f'{{"bench_metric": "ops_per_second", "test": "test_point_query_repeated", "value": {n_queries / elapsed:.2f}, "iterations": {n_queries}, "duration_seconds": {elapsed:.6f}}}')
