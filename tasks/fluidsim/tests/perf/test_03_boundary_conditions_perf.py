"""Performance benchmarks for Stage 3: Boundary conditions and obstacles."""
import time
import pytest


class TestChannelFlowPerf:
    def test_channel_inflow_outflow_32x32(self, engine):
        """Channel flow with inflow/outflow on 32x32 grid."""
        engine.create(nx=32, ny=32, lx=2.0, ly=1.0, viscosity=0.05)
        engine.set_boundary("left", "inflow", profile="uniform", velocity=[1.0, 0.0])
        engine.set_boundary("right", "outflow")
        engine.set_boundary("top", "no_slip")
        engine.set_boundary("bottom", "no_slip")

        start = time.perf_counter()
        resp = engine.solve_steady(tolerance=1e-5, max_iterations=50000)
        elapsed = time.perf_counter() - start

        assert resp["converged"] is True
        print(f'{{"bench_metric": "solve_time_seconds", "test": "test_channel_inflow_outflow_32x32", "value": {elapsed:.6f}, "grid": "32x32", "iterations": {resp["iterations"]}}}')

    def test_channel_inflow_outflow_64x64(self, engine):
        """Channel flow with inflow/outflow on 64x64 grid."""
        engine.create(nx=64, ny=64, lx=2.0, ly=1.0, viscosity=0.05)
        engine.set_boundary("left", "inflow", profile="uniform", velocity=[1.0, 0.0])
        engine.set_boundary("right", "outflow")
        engine.set_boundary("top", "no_slip")
        engine.set_boundary("bottom", "no_slip")

        start = time.perf_counter()
        resp = engine.solve_steady(tolerance=1e-5, max_iterations=100000)
        elapsed = time.perf_counter() - start

        assert resp["converged"] is True
        print(f'{{"bench_metric": "solve_time_seconds", "test": "test_channel_inflow_outflow_64x64", "value": {elapsed:.6f}, "grid": "64x64", "iterations": {resp["iterations"]}}}')


class TestCylinderFlowPerf:
    def test_cylinder_flow_64x32(self, engine):
        """Flow around cylinder on 64x32 grid."""
        engine.create(nx=64, ny=32, lx=4.0, ly=1.0, viscosity=0.05)
        engine.set_boundary("left", "inflow", profile="uniform", velocity=[1.0, 0.0])
        engine.set_boundary("right", "outflow")
        engine.set_boundary("top", "no_slip")
        engine.set_boundary("bottom", "no_slip")
        engine.add_obstacle("circle", center=[1.0, 0.5], radius=0.1)

        start = time.perf_counter()
        resp = engine.solve_steady(tolerance=1e-4, max_iterations=100000)
        elapsed = time.perf_counter() - start

        assert resp["converged"] is True
        print(f'{{"bench_metric": "solve_time_seconds", "test": "test_cylinder_flow_64x32", "value": {elapsed:.6f}, "grid": "64x32", "iterations": {resp["iterations"]}}}')
