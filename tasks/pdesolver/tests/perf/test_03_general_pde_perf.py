"""Performance benchmarks for Stage 3: General PDE operations."""
import time
import numpy as np
import pdesolver


def fisher_rhs(fields, operators, x, y, t, params):
    u = fields["u"]
    lap_u = operators["laplacian"]
    D = params["D"]
    r = params["r"]
    return D * lap_u + r * u * (1 - u)


def prey_rhs(fields, operators, x, y, t, params):
    u = fields["u"]
    v = fields["v"]
    lap_u = operators["laplacian"]
    return params["D_u"] * lap_u + u * (1 - u) - u * v


def pred_rhs(fields, operators, x, y, t, params):
    u = fields["u"]
    v = fields["v"]
    lap_v = operators["laplacian"]
    return params["D_v"] * lap_v + u * v - params["m"] * v


class TestGeneralPDEPerf:
    """Measure throughput of nonlinear RHS evaluation, coupled systems, and parameter changes."""

    def test_nonlinear_rhs_throughput(self):
        """Time 500 steps of Fisher-KPP equation on 101x101 grid."""
        sim = pdesolver.Simulation(x_range=(0, 10), y_range=(0, 10), nx=101, ny=101)
        sim.add_field("u", rhs=fisher_rhs, params={"D": 1.0, "r": 1.0})
        sim.set_initial_condition("u", lambda x, y: np.where(x < 2.0, 1.0, 0.0))
        sim.set_bc("u", "all", "neumann", flux=0.0)

        N = 500
        dt = 0.005

        start = time.perf_counter()
        sim.step(dt=dt, n_steps=N)
        elapsed = time.perf_counter() - start

        value = N / elapsed
        print(f'{{"bench_metric": "ops_per_second", "test": "test_nonlinear_rhs_throughput", "value": {value:.2f}, "iterations": {N}, "duration_seconds": {elapsed:.6f}}}')

    def test_coupled_system_throughput(self):
        """Time 200 steps of 2-field coupled system on 101x101 grid."""
        sim = pdesolver.Simulation(x_range=(0, 10), y_range=(0, 10), nx=101, ny=101)

        sim.add_field("u", rhs=prey_rhs, params={"D_u": 0.1})
        sim.set_initial_condition("u", lambda x, y: 0.8 + 0.1 * np.sin(np.pi * x / 10) * np.sin(np.pi * y / 10))
        sim.set_bc("u", "all", "neumann", flux=0.0)

        sim.add_field("v", rhs=pred_rhs, params={"D_v": 0.05, "m": 0.3})
        sim.set_initial_condition("v", lambda x, y: 0.2 + 0.1 * np.cos(np.pi * x / 10) * np.cos(np.pi * y / 10))
        sim.set_bc("v", "all", "neumann", flux=0.0)

        N = 200
        dt = 0.005

        start = time.perf_counter()
        sim.step(dt=dt, n_steps=N)
        elapsed = time.perf_counter() - start

        value = N / elapsed
        print(f'{{"bench_metric": "ops_per_second", "test": "test_coupled_system_throughput", "value": {value:.2f}, "iterations": {N}, "duration_seconds": {elapsed:.6f}}}')

    def test_parameter_change_overhead(self):
        """Time 1000 parameter changes on a simulation."""
        def diffusion_rhs(fields, operators, x, y, t, params):
            return params["D"] * operators["laplacian"]

        sim = pdesolver.Simulation(x_range=(0, 1), y_range=(0, 1), nx=101, ny=101)
        sim.add_field("u", rhs=diffusion_rhs, params={"D": 1.0})
        sim.set_initial_condition("u", lambda x, y: np.sin(np.pi * x) * np.sin(np.pi * y))
        sim.set_bc("u", "all", "dirichlet", value=0.0)

        N = 1000

        start = time.perf_counter()
        for i in range(N):
            sim.set_parameter("D", 0.1 + 0.9 * (i / N))
        elapsed = time.perf_counter() - start

        value = N / elapsed
        print(f'{{"bench_metric": "ops_per_second", "test": "test_parameter_change_overhead", "value": {value:.2f}, "iterations": {N}, "duration_seconds": {elapsed:.6f}}}')
