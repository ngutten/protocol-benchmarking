"""Performance benchmarks for Stage 2: Navier-Stokes solver."""
import time
import pytest


class TestCavitySolveThroughput:
    def test_cavity_re100_32x32(self, engine):
        """Cavity Re=100 solve time on 32x32 grid."""
        engine.create(nx=32, ny=32, lx=1.0, ly=1.0, viscosity=0.01)
        engine.set_boundary("top", "velocity", value=[1.0, 0.0])
        engine.set_boundary("bottom", "no_slip")
        engine.set_boundary("left", "no_slip")
        engine.set_boundary("right", "no_slip")

        start = time.perf_counter()
        resp = engine.solve_steady(tolerance=1e-5, max_iterations=50000)
        elapsed = time.perf_counter() - start

        assert resp["converged"] is True
        print(f'{{"bench_metric": "solve_time_seconds", "test": "test_cavity_re100_32x32", "value": {elapsed:.6f}, "grid": "32x32", "iterations": {resp["iterations"]}}}')

    def test_cavity_re100_64x64(self, engine):
        """Cavity Re=100 solve time on 64x64 grid."""
        engine.create(nx=64, ny=64, lx=1.0, ly=1.0, viscosity=0.01)
        engine.set_boundary("top", "velocity", value=[1.0, 0.0])
        engine.set_boundary("bottom", "no_slip")
        engine.set_boundary("left", "no_slip")
        engine.set_boundary("right", "no_slip")

        start = time.perf_counter()
        resp = engine.solve_steady(tolerance=1e-5, max_iterations=100000)
        elapsed = time.perf_counter() - start

        assert resp["converged"] is True
        print(f'{{"bench_metric": "solve_time_seconds", "test": "test_cavity_re100_64x64", "value": {elapsed:.6f}, "grid": "64x64", "iterations": {resp["iterations"]}}}')


class TestTimesteppingThroughput:
    def test_stepping_32x32(self, engine):
        """Time stepping throughput on 32x32 grid."""
        engine.create(nx=32, ny=32, lx=1.0, ly=1.0, viscosity=0.01)
        engine.set_boundary("top", "velocity", value=[1.0, 0.0])
        engine.set_boundary("bottom", "no_slip")
        engine.set_boundary("left", "no_slip")
        engine.set_boundary("right", "no_slip")

        n_steps = 100
        start = time.perf_counter()
        resp = engine.step(dt=0.001, steps=n_steps)
        elapsed = time.perf_counter() - start

        assert resp["steps_completed"] == n_steps
        print(f'{{"bench_metric": "steps_per_second", "test": "test_stepping_32x32", "value": {n_steps / elapsed:.2f}, "iterations": {n_steps}, "duration_seconds": {elapsed:.6f}}}')

    def test_stepping_64x64(self, engine):
        """Time stepping throughput on 64x64 grid."""
        engine.create(nx=64, ny=64, lx=1.0, ly=1.0, viscosity=0.01)
        engine.set_boundary("top", "velocity", value=[1.0, 0.0])
        engine.set_boundary("bottom", "no_slip")
        engine.set_boundary("left", "no_slip")
        engine.set_boundary("right", "no_slip")

        n_steps = 50
        start = time.perf_counter()
        resp = engine.step(dt=0.001, steps=n_steps)
        elapsed = time.perf_counter() - start

        assert resp["steps_completed"] == n_steps
        print(f'{{"bench_metric": "steps_per_second", "test": "test_stepping_64x64", "value": {n_steps / elapsed:.2f}, "iterations": {n_steps}, "duration_seconds": {elapsed:.6f}}}')
