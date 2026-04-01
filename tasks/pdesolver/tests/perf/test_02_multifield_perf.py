"""Performance benchmarks for Stage 2: Multi-field and Poisson operations."""
import time
import numpy as np
import pdesolver


class TestMultifieldPerf:
    """Measure throughput of multi-field stepping, Poisson solves, and static field updates."""

    def test_multifield_step_throughput(self):
        """Time 500 steps with 3 fields on 101x101 grid."""
        sim = pdesolver.Simulation(x_range=(0, 1), y_range=(0, 1), nx=101, ny=101)

        sim.add_field("a", D=1.0)
        sim.set_initial_condition("a", lambda x, y: np.sin(np.pi * x) * np.sin(np.pi * y))
        sim.set_bc("a", "all", "dirichlet", value=0.0)

        sim.add_field("b", D=0.5)
        sim.set_initial_condition("b", lambda x, y: np.cos(np.pi * x) * np.sin(np.pi * y))
        sim.set_bc("b", "all", "dirichlet", value=0.0)

        sim.add_field("c", D=0.1)
        sim.set_initial_condition("c", lambda x, y: np.sin(2 * np.pi * x) * np.sin(np.pi * y))
        sim.set_bc("c", "all", "dirichlet", value=0.0)

        N = 500
        dt = 2e-5  # stable for 101x101 grid with D_max=1.0

        start = time.perf_counter()
        sim.step(dt=dt, n_steps=N)
        elapsed = time.perf_counter() - start

        value = N / elapsed
        print(f'{{"bench_metric": "ops_per_second", "test": "test_multifield_step_throughput", "value": {value:.2f}, "iterations": {N}, "duration_seconds": {elapsed:.6f}}}')

    def test_poisson_solve_throughput(self):
        """Time 10 Poisson solves on 101x101 grid."""
        N = 10

        x = np.linspace(0, 1, 101)
        y = np.linspace(0, 1, 101)
        X, Y = np.meshgrid(x, y, indexing="ij")
        rho_data = -2 * np.pi**2 * np.sin(np.pi * X) * np.sin(np.pi * Y)

        start = time.perf_counter()
        for _ in range(N):
            sim = pdesolver.Simulation(x_range=(0, 1), y_range=(0, 1), nx=101, ny=101)
            sim.add_static_field("rho", data=rho_data)
            sim.add_field("phi")
            sim.set_bc("phi", "all", "dirichlet", value=0.0)
            sim.poisson_solve("phi", source="rho", tol=1e-8)
        elapsed = time.perf_counter() - start

        value = N / elapsed
        print(f'{{"bench_metric": "ops_per_second", "test": "test_poisson_solve_throughput", "value": {value:.2f}, "iterations": {N}, "duration_seconds": {elapsed:.6f}}}')

    def test_static_field_update_throughput(self):
        """Time 1000 static field updates on 101x101 grid."""
        sim = pdesolver.Simulation(x_range=(0, 1), y_range=(0, 1), nx=101, ny=101)

        x = np.linspace(0, 1, 101)
        y = np.linspace(0, 1, 101)
        X, Y = np.meshgrid(x, y, indexing="ij")
        source_data = np.sin(np.pi * X) * np.sin(np.pi * Y)

        sim.add_static_field("source", data=source_data)
        sim.add_field("u", D=1.0, source="source")
        sim.set_initial_condition("u", lambda x, y: np.zeros_like(x))
        sim.set_bc("u", "all", "dirichlet", value=0.0)

        N = 1000

        start = time.perf_counter()
        for i in range(N):
            phase = i * 0.01
            new_data = np.sin(np.pi * X + phase) * np.sin(np.pi * Y)
            sim.update_static_field("source", data=new_data)
        elapsed = time.perf_counter() - start

        value = N / elapsed
        print(f'{{"bench_metric": "ops_per_second", "test": "test_static_field_update_throughput", "value": {value:.2f}, "iterations": {N}, "duration_seconds": {elapsed:.6f}}}')
