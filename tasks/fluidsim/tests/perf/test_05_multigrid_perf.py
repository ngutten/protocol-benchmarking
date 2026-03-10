"""Performance benchmarks for Stage 5: Multigrid solver."""
import time
import pytest


class TestMultigridVsBaseline:
    def test_multigrid_vs_default_32x32(self, engine):
        """Compare multigrid vs default solve time on 32x32."""
        # Default solver
        engine.create(nx=32, ny=32, lx=1.0, ly=1.0, viscosity=0.1, force=[1.0, 0.0])
        engine.set_boundary("top", "no_slip")
        engine.set_boundary("bottom", "no_slip")
        engine.set_boundary("left", "velocity", value=[0.0, 0.0])
        engine.set_boundary("right", "velocity", value=[0.0, 0.0])

        start = time.perf_counter()
        resp_def = engine.solve_steady(tolerance=1e-6, max_iterations=50000)
        elapsed_def = time.perf_counter() - start

        # Multigrid solver
        engine.reset()
        engine.create(nx=32, ny=32, lx=1.0, ly=1.0, viscosity=0.1, force=[1.0, 0.0])
        engine.set_boundary("top", "no_slip")
        engine.set_boundary("bottom", "no_slip")
        engine.set_boundary("left", "velocity", value=[0.0, 0.0])
        engine.set_boundary("right", "velocity", value=[0.0, 0.0])
        engine.set_solver("multigrid", levels=4, cycle="V", pre_smooth=2, post_smooth=2)

        start = time.perf_counter()
        resp_mg = engine.solve_steady(tolerance=1e-6, max_iterations=50000)
        elapsed_mg = time.perf_counter() - start

        assert resp_def["converged"] is True
        assert resp_mg["converged"] is True

        speedup = elapsed_def / elapsed_mg if elapsed_mg > 0 else float('inf')
        print(f'{{"bench_metric": "multigrid_speedup", "test": "test_multigrid_vs_default_32x32", "value": {speedup:.3f}, "default_seconds": {elapsed_def:.6f}, "multigrid_seconds": {elapsed_mg:.6f}}}')

    def test_multigrid_vs_default_64x64(self, engine):
        """Compare multigrid vs default solve time on 64x64."""
        # Default solver
        engine.create(nx=64, ny=64, lx=1.0, ly=1.0, viscosity=0.1, force=[1.0, 0.0])
        engine.set_boundary("top", "no_slip")
        engine.set_boundary("bottom", "no_slip")
        engine.set_boundary("left", "velocity", value=[0.0, 0.0])
        engine.set_boundary("right", "velocity", value=[0.0, 0.0])

        start = time.perf_counter()
        resp_def = engine.solve_steady(tolerance=1e-6, max_iterations=100000)
        elapsed_def = time.perf_counter() - start

        # Multigrid solver
        engine.reset()
        engine.create(nx=64, ny=64, lx=1.0, ly=1.0, viscosity=0.1, force=[1.0, 0.0])
        engine.set_boundary("top", "no_slip")
        engine.set_boundary("bottom", "no_slip")
        engine.set_boundary("left", "velocity", value=[0.0, 0.0])
        engine.set_boundary("right", "velocity", value=[0.0, 0.0])
        engine.set_solver("multigrid", levels=5, cycle="V", pre_smooth=2, post_smooth=2)

        start = time.perf_counter()
        resp_mg = engine.solve_steady(tolerance=1e-6, max_iterations=100000)
        elapsed_mg = time.perf_counter() - start

        assert resp_def["converged"] is True
        assert resp_mg["converged"] is True

        speedup = elapsed_def / elapsed_mg if elapsed_mg > 0 else float('inf')
        print(f'{{"bench_metric": "multigrid_speedup", "test": "test_multigrid_vs_default_64x64", "value": {speedup:.3f}, "default_seconds": {elapsed_def:.6f}, "multigrid_seconds": {elapsed_mg:.6f}}}')


class TestMultigridScaling:
    def test_multigrid_cavity_32x32(self, engine):
        """Multigrid cavity solve on 32x32."""
        engine.create(nx=32, ny=32, lx=1.0, ly=1.0, viscosity=0.01)
        engine.set_boundary("top", "velocity", value=[1.0, 0.0])
        engine.set_boundary("bottom", "no_slip")
        engine.set_boundary("left", "no_slip")
        engine.set_boundary("right", "no_slip")
        engine.set_solver("multigrid", levels=4, cycle="V", pre_smooth=2, post_smooth=2)

        start = time.perf_counter()
        resp = engine.solve_steady(tolerance=1e-5, max_iterations=50000)
        elapsed = time.perf_counter() - start

        assert resp["converged"] is True
        print(f'{{"bench_metric": "solve_time_seconds", "test": "test_multigrid_cavity_32x32", "value": {elapsed:.6f}, "grid": "32x32", "iterations": {resp["iterations"]}}}')

    def test_multigrid_cavity_64x64(self, engine):
        """Multigrid cavity solve on 64x64."""
        engine.create(nx=64, ny=64, lx=1.0, ly=1.0, viscosity=0.01)
        engine.set_boundary("top", "velocity", value=[1.0, 0.0])
        engine.set_boundary("bottom", "no_slip")
        engine.set_boundary("left", "no_slip")
        engine.set_boundary("right", "no_slip")
        engine.set_solver("multigrid", levels=5, cycle="V", pre_smooth=2, post_smooth=2)

        start = time.perf_counter()
        resp = engine.solve_steady(tolerance=1e-5, max_iterations=100000)
        elapsed = time.perf_counter() - start

        assert resp["converged"] is True
        print(f'{{"bench_metric": "solve_time_seconds", "test": "test_multigrid_cavity_64x64", "value": {elapsed:.6f}, "grid": "64x64", "iterations": {resp["iterations"]}}}')
