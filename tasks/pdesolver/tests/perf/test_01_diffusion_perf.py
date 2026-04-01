"""Performance benchmarks for Stage 1: Diffusion solver operations."""
import time
import numpy as np
import pdesolver


class TestDiffusionPerf:
    """Measure throughput of core diffusion stepping and grid operations."""

    def test_euler_step_throughput_small(self):
        """Time 1000 Euler steps on a 51x51 grid with D=1.0, Dirichlet BCs."""
        sim = pdesolver.Simulation(x_range=(0, 1), y_range=(0, 1), nx=51, ny=51)
        sim.add_field("u", D=1.0)
        sim.set_initial_condition("u", lambda x, y: np.sin(np.pi * x) * np.sin(np.pi * y))
        sim.set_bc("u", "all", "dirichlet", value=0.0)

        N = 1000
        dt = 8e-5  # stable for 51x51 grid

        start = time.perf_counter()
        sim.step(dt=dt, n_steps=N)
        elapsed = time.perf_counter() - start

        u = sim.get_field("u")
        assert not np.any(np.isnan(u)), "Field contains NaN values"
        assert u.shape == (51, 51), f"Unexpected shape {u.shape}"

        value = N / elapsed
        print(f'{{"bench_metric": "ops_per_second", "test": "test_euler_step_throughput_small", "value": {value:.2f}, "iterations": {N}, "duration_seconds": {elapsed:.6f}}}')

    def test_euler_step_throughput_large(self):
        """Time 200 Euler steps on a 201x201 grid."""
        sim = pdesolver.Simulation(x_range=(0, 1), y_range=(0, 1), nx=201, ny=201)
        sim.add_field("u", D=1.0)
        sim.set_initial_condition("u", lambda x, y: np.sin(np.pi * x) * np.sin(np.pi * y))
        sim.set_bc("u", "all", "dirichlet", value=0.0)

        N = 200
        dx = 1.0 / 200
        dt = 0.2 * dx**2  # stable for 201x201 grid

        start = time.perf_counter()
        sim.step(dt=dt, n_steps=N)
        elapsed = time.perf_counter() - start

        u = sim.get_field("u")
        assert not np.any(np.isnan(u)), "Field contains NaN values"
        assert u.shape == (201, 201), f"Unexpected shape {u.shape}"

        value = N / elapsed
        print(f'{{"bench_metric": "ops_per_second", "test": "test_euler_step_throughput_large", "value": {value:.2f}, "iterations": {N}, "duration_seconds": {elapsed:.6f}}}')

    def test_grid_creation_throughput(self):
        """Time creating 100 Simulation objects with 101x101 grids."""
        N = 100

        start = time.perf_counter()
        for _ in range(N):
            sim = pdesolver.Simulation(x_range=(0, 1), y_range=(0, 1), nx=101, ny=101)
            sim.add_field("u", D=1.0)
            sim.set_initial_condition("u", lambda x, y: np.sin(np.pi * x) * np.sin(np.pi * y))
            sim.set_bc("u", "all", "dirichlet", value=0.0)
        elapsed = time.perf_counter() - start

        # Verify the last simulation object is valid
        u = sim.get_field("u")
        assert not np.any(np.isnan(u)), "Field contains NaN values"
        assert u.shape == (101, 101), f"Unexpected shape {u.shape}"

        value = N / elapsed
        print(f'{{"bench_metric": "ops_per_second", "test": "test_grid_creation_throughput", "value": {value:.2f}, "iterations": {N}, "duration_seconds": {elapsed:.6f}}}')

    def test_field_read_throughput(self):
        """Time 1000 calls to get_field("u")."""
        sim = pdesolver.Simulation(x_range=(0, 1), y_range=(0, 1), nx=101, ny=101)
        sim.add_field("u", D=1.0)
        sim.set_initial_condition("u", lambda x, y: np.sin(np.pi * x) * np.sin(np.pi * y))
        sim.set_bc("u", "all", "dirichlet", value=0.0)

        # Run a few steps so the field has nontrivial values
        sim.step(dt=2e-5, n_steps=10)

        N = 1000
        start = time.perf_counter()
        for _ in range(N):
            u = sim.get_field("u")
        elapsed = time.perf_counter() - start

        assert not np.any(np.isnan(u)), "Field contains NaN values"
        assert u.shape == (101, 101), f"Unexpected shape {u.shape}"
        assert np.max(np.abs(u)) > 0, "Field is all zeros unexpectedly"

        value = N / elapsed
        print(f'{{"bench_metric": "ops_per_second", "test": "test_field_read_throughput", "value": {value:.2f}, "iterations": {N}, "duration_seconds": {elapsed:.6f}}}')
