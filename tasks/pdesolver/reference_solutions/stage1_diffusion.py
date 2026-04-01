"""Stage 1: Diffusion reference solutions."""

import sys
import os
import numpy as np
import torch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pde_solver import (
    RegularGrid2D,
    RegularField2D,
    RegularLaplacian2D,
    SpectralLaplacian2D,
    DirichletBC,
    NeumannBC,
    RobinBC,
    PeriodicBC,
    BoundaryConditionSet,
    ForwardEuler,
)

OUTDIR = os.path.join(os.path.dirname(__file__), "data")
os.makedirs(OUTDIR, exist_ok=True)

DTYPE = torch.float64
ALL_SIDES = ["bottom", "top", "left", "right"]


def make_grid(nx, ny, lx, ly, periodic=False):
    return RegularGrid2D(nx=nx, ny=ny, lx=lx, ly=ly, periodic=periodic, dtype=DTYPE)


def get_xy(grid):
    coords = grid.node_coords
    x = coords[:, 0].reshape(grid.grid_shape)
    y = coords[:, 1].reshape(grid.grid_shape)
    return x, y


def run_euler_loop(u, lap, bcs, dt, t, target_t):
    """Run forward Euler from t to target_t, return (u, t)."""
    stepper = ForwardEuler()
    while t < target_t - dt / 2:
        u = stepper.step(u, lap, dt, bcs=bcs, t=t)
        t += dt
    return u, t


def run_ref_1_1():
    """REF-1.1: Gaussian blob diffusion."""
    print("Running REF-1.1: Gaussian blob diffusion...")
    # Domain [0,10]x[0,10], 101x101 => dx=0.1, D=1.0
    # dt_max = 0.1^2/4 = 0.0025; dt=0.001 is safe
    grid = make_grid(101, 101, 10.0, 10.0)
    x, y = get_xy(grid)

    u0_data = torch.exp(-((x - 5) ** 2 + (y - 5) ** 2) / 0.5)
    u = RegularField2D(grid, u0_data)

    bcs = BoundaryConditionSet([DirichletBC("all", 0.0)])
    lap = RegularLaplacian2D(grid, boundary_conditions=[DirichletBC("all", 0.0)])

    dt = 0.001
    t = 0.0
    snapshots = {}

    for snap_t in [0.1, 0.3, 0.5]:
        u, t = run_euler_loop(u, lap, bcs, dt, t, snap_t)
        snapshots[f"u_t{snap_t}"] = u.grid_view.numpy().copy()
        print(f"  t={t:.4f}, max={u.grid_view.max().item():.6f}")

    np.savez(os.path.join(OUTDIR, "ref_1_1.npz"), x=x.numpy(), y=y.numpy(), **snapshots)
    print("  Saved ref_1_1.npz")


def run_ref_1_2():
    """REF-1.2: Steady-state Laplace."""
    print("Running REF-1.2: Steady-state Laplace...")
    # Domain [0,1]x[0,1], 101x101 => dx=0.01, D=1.0
    # dt_max = 0.01^2/4 = 2.5e-5; spec says dt=1e-4 which is unstable!
    # Use dt=2e-5 for stability
    grid = make_grid(101, 101, 1.0, 1.0)
    x, y = get_xy(grid)

    u = RegularField2D(grid, torch.zeros(grid.grid_shape, dtype=DTYPE))

    dir_bcs = [
        DirichletBC("top", 1.0),
        DirichletBC("bottom", 0.0),
        DirichletBC("left", 0.0),
        DirichletBC("right", 0.0),
    ]
    bcs = BoundaryConditionSet(dir_bcs)
    bcs.apply_all(u, 0.0)
    lap = RegularLaplacian2D(grid, boundary_conditions=dir_bcs)

    dt = 2e-5
    t = 0.0
    stepper = ForwardEuler()
    snapshots = {}
    snap_times = [0.5, 1.0]
    converged_t = None
    converged_field = None
    step_count = 0

    while t < 5.0:
        u_old = u.grid_view.clone()
        u = stepper.step(u, lap, dt, bcs=bcs, t=t)
        t += dt
        step_count += 1

        for snap_t in snap_times:
            if abs(t - snap_t) < dt / 2 and f"u_t{snap_t}" not in snapshots:
                snapshots[f"u_t{snap_t}"] = u.grid_view.numpy().copy()
                print(f"  Snapshot at t={t:.4f}")

        max_change = (u.grid_view - u_old).abs().max().item()
        if max_change < 1e-8 and converged_t is None:
            converged_t = t
            converged_field = u.grid_view.numpy().copy()
            print(f"  Converged at t={t:.4f}, max_change={max_change:.2e}, steps={step_count}")
            # Continue to capture remaining snapshots, then stop
            remaining = [st for st in snap_times if f"u_t{st}" not in snapshots]
            if not remaining:
                break
            # Fast-forward: the field is essentially static now

        if step_count % 50000 == 0:
            print(f"  t={t:.4f}, max_change={max_change:.2e}")

    if converged_field is None:
        converged_t = t
        converged_field = u.grid_view.numpy().copy()
        print(f"  Reached t={t:.4f} without full convergence")

    snapshots["u_converged"] = converged_field
    snapshots["converged_time"] = np.array([converged_t])

    # Analytical series solution (truncated at n=99)
    u_analytical = np.zeros((101, 101))
    x_np, y_np = x.numpy(), y.numpy()
    for n in range(1, 100, 2):
        u_analytical += (4.0 / (n * np.pi)) * np.sin(n * np.pi * x_np) * np.sinh(n * np.pi * y_np) / np.sinh(n * np.pi)
    snapshots["u_analytical"] = u_analytical

    np.savez(os.path.join(OUTDIR, "ref_1_2.npz"), x=x_np, y=y_np, **snapshots)
    print("  Saved ref_1_2.npz")


def run_ref_1_3():
    """REF-1.3: Robin cooling."""
    print("Running REF-1.3: Robin cooling...")
    # Domain [0,1]x[0,1], 101x101 => dx=0.01, D=1.0
    # dt_max = 2.5e-5; spec says dt=1e-4 (unstable), use dt=2e-5
    grid = make_grid(101, 101, 1.0, 1.0)
    x, y = get_xy(grid)

    u = RegularField2D(grid, torch.ones(grid.grid_shape, dtype=DTYPE))

    robin_bcs = [RobinBC(side, alpha=1.0, beta=0.5, g=0.0) for side in ALL_SIDES]
    bcs = BoundaryConditionSet(robin_bcs)
    bcs.apply_all(u, 0.0)
    lap = RegularLaplacian2D(grid, boundary_conditions=robin_bcs)

    dt = 2e-5
    t = 0.0
    snapshots = {}

    for snap_t in [0.01, 0.05, 0.1]:
        u, t = run_euler_loop(u, lap, bcs, dt, t, snap_t)
        snapshots[f"u_t{snap_t}"] = u.grid_view.numpy().copy()
        print(f"  t={t:.4f}, max={u.grid_view.max().item():.6f}, min={u.grid_view.min().item():.6f}")

    np.savez(os.path.join(OUTDIR, "ref_1_3.npz"), x=x.numpy(), y=y.numpy(), **snapshots)
    print("  Saved ref_1_3.npz")


def run_ref_1_4():
    """REF-1.4: Periodic sinusoidal."""
    print("Running REF-1.4: Periodic sinusoidal...")
    # Domain [0,2pi]x[0,2pi], 101x101 periodic => dx=2pi/101≈0.0622
    # D=0.1, dt_max(spectral) is stricter. Use manual stepping to be safe.
    grid = make_grid(101, 101, 2 * np.pi, 2 * np.pi, periodic=True)
    x, y = get_xy(grid)

    D = 0.1
    u0_data = torch.sin(x) + 0.5 * torch.cos(2 * y)
    u = RegularField2D(grid, u0_data)

    lap = SpectralLaplacian2D(grid)

    # Spectral stability: k_max=50, D=0.1, dt_max = 2/(D*(2*k_max^2)) = 2/500 = 0.004
    # Use dt=0.003 for safety
    dt = 0.003
    t = 0.0
    snapshots = {}

    for snap_t in [0.5, 1.0, 2.0]:
        while t < snap_t - dt / 2:
            # Manual Euler step: u_new = u + dt * D * lap(u)
            lap_u = lap.apply(u)
            new_data = u.grid_view + dt * D * lap_u.grid_view
            u = RegularField2D(grid, new_data)
            t += dt

        snapshots[f"u_t{snap_t}"] = u.grid_view.numpy().copy()

        u_exact = (torch.sin(x) * np.exp(-D * snap_t)
                   + 0.5 * torch.cos(2 * y) * np.exp(-4 * D * snap_t))
        snapshots[f"u_analytical_t{snap_t}"] = u_exact.numpy()
        err = (u.grid_view - u_exact).abs().max().item()
        print(f"  t={snap_t:.1f}, max_err={err:.6e}")

    np.savez(os.path.join(OUTDIR, "ref_1_4.npz"), x=x.numpy(), y=y.numpy(), **snapshots)
    print("  Saved ref_1_4.npz")


def run_ref_1_5():
    """REF-1.5: Time-dependent Dirichlet."""
    print("Running REF-1.5: Time-dependent Dirichlet...")
    # Domain [0,1]x[0,1], 101x101 => dx=0.01, D=1.0
    # dt_max = 2.5e-5; spec says dt=1e-4 (unstable), use dt=2e-5
    grid = make_grid(101, 101, 1.0, 1.0)
    x, y = get_xy(grid)

    u = RegularField2D(grid, torch.zeros(grid.grid_shape, dtype=DTYPE))

    def left_bc_fn(coords, t):
        return torch.sin(torch.tensor(2 * np.pi * t, dtype=DTYPE)) * torch.ones(
            coords.shape[0], dtype=DTYPE, device=coords.device
        )

    dir_bcs = [
        DirichletBC("left", value=left_bc_fn),
        DirichletBC("right", 0.0),
        DirichletBC("top", 0.0),
        DirichletBC("bottom", 0.0),
    ]
    bcs = BoundaryConditionSet(dir_bcs)
    bcs.apply_all(u, 0.0)
    lap = RegularLaplacian2D(grid, boundary_conditions=dir_bcs)

    dt = 2e-5
    t = 0.0
    snapshots = {}

    for snap_t in [0.1, 0.25, 0.5]:
        u, t = run_euler_loop(u, lap, bcs, dt, t, snap_t)
        snapshots[f"u_t{snap_t}"] = u.grid_view.numpy().copy()
        left_vals = u.grid_view[:, 0].numpy().copy()
        snapshots[f"left_boundary_t{snap_t}"] = left_vals
        print(f"  t={t:.4f}, left_bc={np.sin(2*np.pi*t):.4f}, left_edge_mean={left_vals.mean():.4f}")

    np.savez(os.path.join(OUTDIR, "ref_1_5.npz"), x=x.numpy(), y=y.numpy(), **snapshots)
    print("  Saved ref_1_5.npz")


def run_ref_1_6():
    """REF-1.6: Grid convergence (coarse and fine)."""
    print("Running REF-1.6: Grid convergence...")

    for label, nx, dt in [("coarse", 51, 8e-5), ("fine", 101, 2e-5)]:
        print(f"  {label}: {nx}x{nx}, dt={dt}")
        grid = make_grid(nx, nx, 1.0, 1.0)
        x, y = get_xy(grid)

        u0_data = torch.sin(np.pi * x) * torch.sin(np.pi * y)
        u = RegularField2D(grid, u0_data)

        bcs = BoundaryConditionSet([DirichletBC("all", 0.0)])
        lap = RegularLaplacian2D(grid, boundary_conditions=[DirichletBC("all", 0.0)])

        u, t = run_euler_loop(u, lap, bcs, dt, 0.0, 0.05)

        u_exact = torch.sin(np.pi * x) * torch.sin(np.pi * y) * np.exp(-2 * np.pi ** 2 * 0.05)
        l2_err = torch.sqrt(((u.grid_view - u_exact) ** 2).mean()).item()
        print(f"    t={t:.6f}, L2_error={l2_err:.6e}")

        suffix = "a" if label == "coarse" else "b"
        np.savez(
            os.path.join(OUTDIR, f"ref_1_6{suffix}.npz"),
            x=x.numpy(), y=y.numpy(),
            u_t0_05=u.grid_view.numpy(),
            u_analytical=u_exact.numpy(),
            l2_error=np.array([l2_err]),
        )
        print(f"    Saved ref_1_6{suffix}.npz")


def run_prop_1_1():
    """PROP-1.1: Neumann conservation."""
    print("Running PROP-1.1: Neumann conservation...")
    # Domain [0,1]x[0,1], 101x101, D=1.0 => dt_max=2.5e-5
    # Spec says dt=1e-4 (unstable), use dt=2e-5
    grid = make_grid(101, 101, 1.0, 1.0)
    x, y = get_xy(grid)

    u0_data = torch.sin(2 * np.pi * x) * torch.cos(np.pi * y) + 1.5
    u = RegularField2D(grid, u0_data)

    neumann_bcs = [NeumannBC(side, flux=0.0) for side in ALL_SIDES]
    bcs = BoundaryConditionSet(neumann_bcs)
    lap = RegularLaplacian2D(grid, boundary_conditions=neumann_bcs)

    dt = 2e-5
    t = 0.0
    dx, dy = grid.dx, grid.dy
    check_times = [0.0, 0.01, 0.05, 0.1]
    integrals = {}

    integral_0 = (u.grid_view.sum() * dx * dy).item()
    integrals["integral_t0.0"] = integral_0
    print(f"  t=0.0, integral={integral_0:.8f}")

    for check_t in check_times[1:]:
        u, t = run_euler_loop(u, lap, bcs, dt, t, check_t)
        integral = (u.grid_view.sum() * dx * dy).item()
        integrals[f"integral_t{check_t}"] = integral
        rel_err = abs(integral - integral_0) / abs(integral_0)
        print(f"  t={t:.4f}, integral={integral:.8f}, rel_err={rel_err:.2e}")

    np.savez(
        os.path.join(OUTDIR, "prop_1_1.npz"),
        **{k: np.array([v]) for k, v in integrals.items()},
    )
    print("  Saved prop_1_1.npz")


def run_prop_1_2():
    """PROP-1.2: Energy dissipation."""
    print("Running PROP-1.2: Energy dissipation...")
    # Same setup as REF-1.1: [0,10]x[0,10], 101x101, D=1.0, dt=0.001 (safe)
    grid = make_grid(101, 101, 10.0, 10.0)
    x, y = get_xy(grid)

    u0_data = torch.exp(-((x - 5) ** 2 + (y - 5) ** 2) / 0.5)
    u = RegularField2D(grid, u0_data)

    bcs = BoundaryConditionSet([DirichletBC("all", 0.0)])
    lap = RegularLaplacian2D(grid, boundary_conditions=[DirichletBC("all", 0.0)])

    dt = 0.001
    t = 0.0
    dx, dy = grid.dx, grid.dy
    check_times = [0.0, 0.05, 0.1, 0.2, 0.3, 0.5]
    energies = {}

    energy_0 = ((u.grid_view ** 2).sum() * dx * dy).item()
    energies["energy_t0.0"] = energy_0
    print(f"  t=0.0, energy={energy_0:.8f}")

    for check_t in check_times[1:]:
        u, t = run_euler_loop(u, lap, bcs, dt, t, check_t)
        energy = ((u.grid_view ** 2).sum() * dx * dy).item()
        energies[f"energy_t{check_t}"] = energy
        print(f"  t={t:.4f}, energy={energy:.8f}")

    vals = [energies[f"energy_t{ct}"] for ct in check_times]
    monotone = all(vals[i] > vals[i + 1] for i in range(len(vals) - 1))
    print(f"  Monotonically decreasing: {monotone}")

    np.savez(
        os.path.join(OUTDIR, "prop_1_2.npz"),
        **{k: np.array([v]) for k, v in energies.items()},
        monotone=np.array([monotone]),
    )
    print("  Saved prop_1_2.npz")


def run_all():
    run_ref_1_1()
    run_ref_1_2()
    run_ref_1_3()
    run_ref_1_4()
    run_ref_1_5()
    run_ref_1_6()
    run_prop_1_1()
    run_prop_1_2()


if __name__ == "__main__":
    run_all()
