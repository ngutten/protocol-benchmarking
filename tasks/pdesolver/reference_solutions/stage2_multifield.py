"""Stage 2: Multiple Fields reference solutions."""

import sys
import os
import numpy as np
import torch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pde_solver import (
    RegularGrid2D,
    RegularField2D,
    RegularLaplacian2D,
    DirichletBC,
    BoundaryConditionSet,
    ForwardEuler,
    PoissonSolver,
)

OUTDIR = os.path.join(os.path.dirname(__file__), "data")
os.makedirs(OUTDIR, exist_ok=True)

DTYPE = torch.float64


def make_grid(nx, ny, lx, ly, periodic=False):
    return RegularGrid2D(nx=nx, ny=ny, lx=lx, ly=ly, periodic=periodic, dtype=DTYPE)


def get_xy(grid):
    coords = grid.node_coords
    x = coords[:, 0].reshape(grid.grid_shape)
    y = coords[:, 1].reshape(grid.grid_shape)
    return x, y


def run_ref_2_1():
    """REF-2.1: Two-field diffusion."""
    print("Running REF-2.1: Two-field diffusion...")
    grid = make_grid(101, 101, 1.0, 1.0)
    x, y = get_xy(grid)

    ic = torch.sin(np.pi * x) * torch.sin(np.pi * y)

    bcs = BoundaryConditionSet([DirichletBC("all", 0.0)])
    bc_list = [DirichletBC("all", 0.0)]

    stepper = ForwardEuler()
    # dx=0.01, D_max=1.0 => dt_max=2.5e-5; use dt=2e-5
    dt = 2e-5
    snap_times = [0.05, 0.1]

    results = {}
    for name, D in [("a", 1.0), ("b", 0.1)]:
        lap = RegularLaplacian2D(grid, boundary_conditions=bc_list)
        scaled_lap = D * lap
        u = RegularField2D(grid, ic.clone())
        bcs.apply_all(u, 0.0)
        t = 0.0

        for snap_t in snap_times:
            while t < snap_t - dt / 2:
                u = stepper.step(u, scaled_lap, dt, bcs=bcs, t=t)
                t += dt
            results[f"{name}_t{snap_t}"] = u.grid_view.numpy().copy()

            # Analytical
            u_exact = torch.sin(np.pi * x) * torch.sin(np.pi * y) * np.exp(-2 * np.pi ** 2 * D * snap_t)
            err = (u.grid_view - u_exact).abs().max().item()
            print(f"  Field {name} at t={snap_t}: max_err={err:.6e}")

    np.savez(
        os.path.join(OUTDIR, "ref_2_1.npz"),
        x=x.numpy(),
        y=y.numpy(),
        **results,
    )
    print("  Saved ref_2_1.npz")


def run_ref_2_2():
    """REF-2.2: Poisson via static source field."""
    print("Running REF-2.2: Poisson via static source field...")
    grid = make_grid(101, 101, 1.0, 1.0)
    x, y = get_xy(grid)

    # Source: rho = -2*pi^2 * sin(pi*x) * sin(pi*y)
    rho_data = -2 * np.pi ** 2 * torch.sin(np.pi * x) * torch.sin(np.pi * y)
    rho = RegularField2D(grid, rho_data)

    # Solve laplacian(phi) = rho with Dirichlet phi=0
    solver = PoissonSolver(
        grid=grid,
        bcs=[DirichletBC("all", 0.0)],
        max_iter=5000,
        tol=1e-8,
    )

    phi0 = RegularField2D(grid, torch.zeros(grid.grid_shape, dtype=DTYPE))
    phi = solver.solve(rho, initial_guess=phi0)

    # Analytical solution: phi = sin(pi*x)*sin(pi*y)
    phi_exact = torch.sin(np.pi * x) * torch.sin(np.pi * y)
    err = (phi.grid_view - phi_exact).abs().max().item()
    print(f"  Max error vs analytical: {err:.6e}")

    # Compute residual: max|laplacian(phi) - rho|
    lap = RegularLaplacian2D(grid, boundary_conditions=[DirichletBC("all", 0.0)])
    lap_phi = lap.apply(phi)
    residual = (lap_phi.grid_view - rho.grid_view).abs().max().item()
    print(f"  Max residual: {residual:.6e}")

    np.savez(
        os.path.join(OUTDIR, "ref_2_2.npz"),
        x=x.numpy(),
        y=y.numpy(),
        phi=phi.grid_view.numpy(),
        phi_analytical=phi_exact.numpy(),
        rho=rho_data.numpy(),
        max_residual=np.array([residual]),
    )
    print("  Saved ref_2_2.npz")


def run_ref_2_3():
    """REF-2.3: Stability monitor reference run."""
    print("Running REF-2.3: Stability monitor reference run...")
    grid = make_grid(101, 101, 1.0, 1.0)
    x, y = get_xy(grid)

    u0_data = torch.sin(np.pi * x) * torch.sin(2 * np.pi * y)
    u = RegularField2D(grid, u0_data)

    bcs = BoundaryConditionSet([DirichletBC("all", 0.0)])
    lap = RegularLaplacian2D(grid, boundary_conditions=[DirichletBC("all", 0.0)])
    stepper = ForwardEuler()

    dt = 1e-5
    t = 0.0
    snapshots = {}
    snap_times = [0.01, 0.02]

    for snap_t in snap_times:
        while t < snap_t - dt / 2:
            u = stepper.step(u, lap, dt, bcs=bcs, t=t)
            t += dt
        snapshots[f"u_t{snap_t}"] = u.grid_view.numpy().copy()
        print(f"  t={t:.6f}, max={u.grid_view.max().item():.6f}")

    np.savez(
        os.path.join(OUTDIR, "ref_2_3.npz"),
        x=x.numpy(),
        y=y.numpy(),
        **snapshots,
    )
    print("  Saved ref_2_3.npz")


def run_ref_2_4():
    """REF-2.4: Static field update."""
    print("Running REF-2.4: Static field update...")
    grid = make_grid(101, 101, 1.0, 1.0)
    x, y = get_xy(grid)

    u = RegularField2D(grid, torch.zeros(grid.grid_shape, dtype=DTYPE))

    bcs = BoundaryConditionSet([DirichletBC("all", 0.0)])
    lap = RegularLaplacian2D(grid, boundary_conditions=[DirichletBC("all", 0.0)])
    stepper = ForwardEuler()

    # dx=0.01, D=1.0 => dt_max=2.5e-5; use dt=2e-5
    # Adjust step counts to reach same target times:
    # Phase 1: 500 steps * 2e-5 = 0.01; Phase 2: 500 steps * 2e-5 = 0.01
    dt = 2e-5
    snapshots = {}

    # Phase 1: source = 5.0 * sin(pi*x) * sin(pi*y), 500 steps
    source1 = 5.0 * torch.sin(np.pi * x) * torch.sin(np.pi * y)
    t = 0.0
    for _ in range(500):
        lap_u = lap.apply(u)
        new_data = u.grid_view + dt * (lap_u.grid_view + source1)
        u = RegularField2D(grid, new_data)
        bcs.apply_all(u, t + dt)
        t += dt

    snapshots["u_t0.01"] = u.grid_view.numpy().copy()
    print(f"  Phase 1 done, t={t:.4f}, max={u.grid_view.max().item():.6f}")

    # Phase 2: source = 5.0 * sin(2*pi*x) * sin(2*pi*y), 500 steps
    source2 = 5.0 * torch.sin(2 * np.pi * x) * torch.sin(2 * np.pi * y)
    for _ in range(500):
        lap_u = lap.apply(u)
        new_data = u.grid_view + dt * (lap_u.grid_view + source2)
        u = RegularField2D(grid, new_data)
        bcs.apply_all(u, t + dt)
        t += dt

    snapshots["u_t0.02"] = u.grid_view.numpy().copy()
    print(f"  Phase 2 done, t={t:.4f}, max={u.grid_view.max().item():.6f}")

    np.savez(
        os.path.join(OUTDIR, "ref_2_4.npz"),
        x=x.numpy(),
        y=y.numpy(),
        **snapshots,
    )
    print("  Saved ref_2_4.npz")


def run_prop_2_1():
    """PROP-2.1: Vector field divergence and curl."""
    print("Running PROP-2.1: Vector field divergence and curl...")
    from pde_solver import RegularGradient2D, RegularDivergence2D, VectorField2D

    grid = make_grid(101, 101, 2 * np.pi, 2 * np.pi)
    x, y = get_xy(grid)

    # v = (sin(x)*cos(y), -cos(x)*sin(y))
    vx = torch.sin(x) * torch.cos(y)
    vy = -torch.cos(x) * torch.sin(y)

    vx_field = RegularField2D(grid, vx)
    vy_field = RegularField2D(grid, vy)
    v = VectorField2D(grid, vx_field, vy_field)

    # Compute divergence
    div = RegularDivergence2D(grid)
    div_v = div.apply(v)

    # Compute curl (scalar in 2D): dv_y/dx - dv_x/dy
    grad = RegularGradient2D(grid)
    grad_vx = grad.apply(vx_field)
    grad_vy = grad.apply(vy_field)
    curl_v = grad_vy.u.grid_view - grad_vx.v.grid_view

    # Analytical values
    div_exact = torch.zeros_like(x)
    curl_exact = 2 * torch.sin(x) * torch.sin(y)

    # Check interior points only (skip boundary)
    interior = slice(2, -2), slice(2, -2)
    div_err = (div_v.grid_view[interior] - div_exact[interior]).abs().max().item()
    curl_err = (curl_v[interior] - curl_exact[interior]).abs().max().item()
    curl_max = curl_exact[interior].abs().max().item()

    print(f"  Div max error (interior): {div_err:.6e}")
    print(f"  Curl max error (interior): {curl_err:.6e}")
    print(f"  Curl relative error: {curl_err / curl_max:.4e}")

    np.savez(
        os.path.join(OUTDIR, "prop_2_1.npz"),
        divergence=div_v.grid_view.numpy(),
        curl=curl_v.numpy(),
        div_exact=div_exact.numpy(),
        curl_exact=curl_exact.numpy(),
        div_max_error=np.array([div_err]),
        curl_max_error=np.array([curl_err]),
    )
    print("  Saved prop_2_1.npz")


def run_all():
    run_ref_2_1()
    run_ref_2_2()
    run_ref_2_3()
    run_ref_2_4()
    run_prop_2_1()


if __name__ == "__main__":
    run_all()
