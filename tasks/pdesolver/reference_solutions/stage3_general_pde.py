"""Stage 3: General PDE reference solutions."""

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
    PeriodicBC,
    BoundaryConditionSet,
    ForwardEuler,
)

OUTDIR = os.path.join(os.path.dirname(__file__), "data")
os.makedirs(OUTDIR, exist_ok=True)

DTYPE = torch.float64
ALL_SIDES = ["bottom", "top", "left", "right"]


def neumann_zero():
    """Return list of zero-flux Neumann BCs on all sides."""
    return [NeumannBC(side, flux=0.0) for side in ALL_SIDES]


def make_grid(nx, ny, lx, ly, periodic=False):
    return RegularGrid2D(nx=nx, ny=ny, lx=lx, ly=ly, periodic=periodic, dtype=DTYPE)


def get_xy(grid):
    coords = grid.node_coords
    x = coords[:, 0].reshape(grid.grid_shape)
    y = coords[:, 1].reshape(grid.grid_shape)
    return x, y


def run_ref_3_1():
    """REF-3.1: Fisher-KPP traveling wave."""
    print("Running REF-3.1: Fisher-KPP traveling wave...")
    grid = make_grid(401, 11, 40.0, 1.0)
    x, y = get_xy(grid)

    D = 1.0
    r = 1.0

    # IC: step function u=1 if x<5 else 0
    u0_data = (x < 5.0).to(DTYPE)
    u = RegularField2D(grid, u0_data)

    bcs = BoundaryConditionSet(neumann_zero())
    lap = RegularLaplacian2D(grid, boundary_conditions=neumann_zero())
    stepper = ForwardEuler()

    # dx=0.1, dy=0.1, D=1.0 => dt_max = 0.1^2/4 = 0.0025; use dt=0.002
    dt = 0.002
    t = 0.0
    snap_times = [5.0, 10.0, 15.0]
    snapshots = {}

    for snap_t in snap_times:
        while t < snap_t - dt / 2:
            lap_u = lap.apply(u)
            u_gv = u.grid_view
            # du/dt = D*laplacian(u) + r*u*(1-u)
            new_data = u_gv + dt * (D * lap_u.grid_view + r * u_gv * (1 - u_gv))
            u = RegularField2D(grid, new_data)
            bcs.apply_all(u, t + dt)
            t += dt

        snapshots[f"u_t{snap_t}"] = u.grid_view.numpy().copy()

        # Midline profile: y=0.5 is closest row
        ny = grid.ny
        mid_row = ny // 2
        midline = u.grid_view[mid_row, :].numpy().copy()
        snapshots[f"midline_t{snap_t}"] = midline

        print(f"  t={t:.2f}, midline front at ~x={x[0, :].numpy()[midline > 0.5].max():.1f}")

    np.savez(
        os.path.join(OUTDIR, "ref_3_1.npz"),
        x=x.numpy(),
        y=y.numpy(),
        **snapshots,
    )
    print("  Saved ref_3_1.npz")



def run_ref_3_3():
    """REF-3.3: Coupled predator-prey."""
    print("Running REF-3.3: Coupled predator-prey...")
    grid = make_grid(101, 101, 10.0, 10.0)
    x, y = get_xy(grid)

    D_u, D_v = 0.1, 0.05
    m = 0.3

    u0 = 0.8 + 0.1 * torch.sin(np.pi * x / 10) * torch.sin(np.pi * y / 10)
    v0 = 0.2 + 0.1 * torch.cos(np.pi * x / 10) * torch.cos(np.pi * y / 10)
    u = RegularField2D(grid, u0)
    v = RegularField2D(grid, v0)

    bcs = BoundaryConditionSet(neumann_zero())
    lap = RegularLaplacian2D(grid, boundary_conditions=neumann_zero())
    stepper = ForwardEuler()

    dt = 0.005
    t = 0.0
    snap_times = [1.0, 5.0, 10.0]
    snapshots = {}

    for snap_t in snap_times:
        while t < snap_t - dt / 2:
            lap_u_val = lap.apply(u)
            lap_v_val = lap.apply(v)
            u_gv = u.grid_view
            v_gv = v.grid_view

            # du/dt = D_u * laplacian(u) + u*(1-u) - u*v
            new_u = u_gv + dt * (D_u * lap_u_val.grid_view + u_gv * (1 - u_gv) - u_gv * v_gv)
            # dv/dt = D_v * laplacian(v) + u*v - m*v
            new_v = v_gv + dt * (D_v * lap_v_val.grid_view + u_gv * v_gv - m * v_gv)

            u = RegularField2D(grid, new_u)
            v = RegularField2D(grid, new_v)
            bcs.apply_all(u, t + dt)
            bcs.apply_all(v, t + dt)
            t += dt

        snapshots[f"u_t{snap_t}"] = u.grid_view.numpy().copy()
        snapshots[f"v_t{snap_t}"] = v.grid_view.numpy().copy()
        print(f"  t={t:.2f}, u=[{u.grid_view.min().item():.4f},{u.grid_view.max().item():.4f}], "
              f"v=[{v.grid_view.min().item():.4f},{v.grid_view.max().item():.4f}]")

    np.savez(
        os.path.join(OUTDIR, "ref_3_3.npz"),
        x=x.numpy(),
        y=y.numpy(),
        **snapshots,
    )
    print("  Saved ref_3_3.npz")


def angular_diff(a, b):
    """Compute angular difference (a - b) mapped to [-pi, pi)."""
    d = a - b
    return d - 2 * np.pi * torch.round(d / (2 * np.pi))


def run_ref_3_4():
    """REF-3.4: XY model vortex annihilation."""
    print("Running REF-3.4: XY model vortex annihilation...")
    grid = make_grid(201, 201, 10.0, 10.0, periodic=True)
    x, y = get_xy(grid)

    # IC: vortex at (3.5, 5.0), antivortex at (6.5, 5.0)
    theta = torch.atan2(y - 5.0, x - 3.5) - torch.atan2(y - 5.0, x - 6.5)
    # Map to [0, 2*pi)
    theta = theta % (2 * np.pi)
    u = RegularField2D(grid, theta)

    dx = grid.dx
    dy = grid.dy
    # dx=10/201≈0.0498, D=1.0 => dt_max ≈ 0.0498^2/4 ≈ 6.2e-4; use dt=5e-4
    dt = 5e-4
    t = 0.0
    snap_times = [1.0, 5.0, 10.0, 20.0]
    snapshots = {}

    for snap_t in snap_times:
        while t < snap_t - dt / 2:
            # Angular-aware laplacian of theta
            theta_gv = u.grid_view

            # Angular-aware finite differences with periodic BC (roll)
            dtheta_xp = angular_diff(torch.roll(theta_gv, -1, dims=1), theta_gv) / dx
            dtheta_xm = angular_diff(theta_gv, torch.roll(theta_gv, 1, dims=1)) / dx
            d2theta_x = (dtheta_xp - dtheta_xm) / dx

            dtheta_yp = angular_diff(torch.roll(theta_gv, -1, dims=0), theta_gv) / dy
            dtheta_ym = angular_diff(theta_gv, torch.roll(theta_gv, 1, dims=0)) / dy
            d2theta_y = (dtheta_yp - dtheta_ym) / dy

            lap_theta = d2theta_x + d2theta_y

            new_theta = theta_gv + dt * lap_theta
            new_theta = new_theta % (2 * np.pi)
            u = RegularField2D(grid, new_theta)
            t += dt

        theta_gv = u.grid_view

        # Compute energy: E = 0.5 * integral(|grad(theta)|^2) dx dy
        grad_x = angular_diff(torch.roll(theta_gv, -1, dims=1), theta_gv) / dx
        grad_y = angular_diff(torch.roll(theta_gv, -1, dims=0), theta_gv) / dy
        energy = 0.5 * ((grad_x ** 2 + grad_y ** 2).sum() * dx * dy).item()

        # Compute winding numbers around small loops
        winding_1 = compute_winding_number(theta_gv, x, y, 3.5, 5.0, 1.0, dx, dy)
        winding_2 = compute_winding_number(theta_gv, x, y, 6.5, 5.0, 1.0, dx, dy)

        snapshots[f"theta_t{snap_t}"] = theta_gv.numpy().copy()
        snapshots[f"energy_t{snap_t}"] = np.array([energy])
        snapshots[f"winding1_t{snap_t}"] = np.array([winding_1])
        snapshots[f"winding2_t{snap_t}"] = np.array([winding_2])

        print(f"  t={snap_t:.1f}, energy={energy:.4f}, w1={winding_1:.2f}, w2={winding_2:.2f}")

    np.savez(
        os.path.join(OUTDIR, "ref_3_4.npz"),
        x=x.numpy(),
        y=y.numpy(),
        **snapshots,
    )
    print("  Saved ref_3_4.npz")


def compute_winding_number(theta, x, y, cx, cy, radius, dx, dy):
    """Compute winding number around a loop centered at (cx, cy) with given radius."""
    # Sample points on a circle
    n_pts = 200
    angles = np.linspace(0, 2 * np.pi, n_pts, endpoint=False)
    loop_x = cx + radius * np.cos(angles)
    loop_y = cy + radius * np.sin(angles)

    # Interpolate theta at loop points (nearest neighbor for simplicity)
    theta_np = theta.numpy()
    x_np = x[0, :].numpy()
    y_np = y[:, 0].numpy()

    theta_vals = []
    for lx, ly in zip(loop_x, loop_y):
        # Find nearest grid indices
        ix = np.argmin(np.abs(x_np - lx))
        iy = np.argmin(np.abs(y_np - ly))
        theta_vals.append(theta_np[iy, ix])

    theta_vals = np.array(theta_vals)

    # Winding number = (1/2*pi) * sum of angular differences around loop
    dtheta = np.diff(theta_vals, append=theta_vals[0])
    # Map to [-pi, pi)
    dtheta = dtheta - 2 * np.pi * np.round(dtheta / (2 * np.pi))
    winding = np.sum(dtheta) / (2 * np.pi)

    return winding


def run_ref_3_5():
    """REF-3.5: Parameter modification."""
    print("Running REF-3.5: Parameter modification...")
    grid = make_grid(101, 101, 1.0, 1.0)
    x, y = get_xy(grid)

    ic = torch.sin(np.pi * x) * torch.sin(np.pi * y)
    u = RegularField2D(grid, ic)

    bcs = BoundaryConditionSet([DirichletBC("all", 0.0)])
    bc_list = [DirichletBC("all", 0.0)]
    stepper = ForwardEuler()

    # dx=0.01, D=1.0 => dt_max=2.5e-5; use dt=2e-5
    # Phase 1: 1000 steps * 2e-5 = 0.02; Phase 2: 4000 steps * 2e-5 = 0.08
    dt = 2e-5
    snapshots = {}

    # Phase 1: D = 1.0, 1000 timesteps to t=0.02
    D = 1.0
    lap = RegularLaplacian2D(grid, boundary_conditions=bc_list)
    scaled_lap = D * lap
    t = 0.0
    for _ in range(1000):
        u = stepper.step(u, scaled_lap, dt, bcs=bcs, t=t)
        t += dt

    snapshots["u_t0.02"] = u.grid_view.numpy().copy()

    # Analytical for phase 1
    u_exact_1 = torch.sin(np.pi * x) * torch.sin(np.pi * y) * np.exp(-2 * np.pi ** 2 * 1.0 * 0.02)
    err1 = (u.grid_view - u_exact_1).abs().max().item()
    print(f"  Phase 1 (t=0.02): max_err={err1:.6e}")

    # Phase 2: D = 0.1, 4000 timesteps to t=0.10
    D = 0.1
    scaled_lap = D * lap
    for _ in range(4000):
        u = stepper.step(u, scaled_lap, dt, bcs=bcs, t=t)
        t += dt

    snapshots["u_t0.10"] = u.grid_view.numpy().copy()

    # Analytical for phase 2: amplitude at t=0.02 was exp(-2*pi^2*0.02)
    # Then decays with D=0.1 for dt=0.08 more
    amp_phase1 = np.exp(-2 * np.pi ** 2 * 1.0 * 0.02)
    amp_phase2 = amp_phase1 * np.exp(-2 * np.pi ** 2 * 0.1 * 0.08)
    u_exact_2 = torch.sin(np.pi * x) * torch.sin(np.pi * y) * amp_phase2
    err2 = (u.grid_view - u_exact_2).abs().max().item()
    print(f"  Phase 2 (t=0.10): max_err={err2:.6e}")

    snapshots["u_analytical_t0.02"] = u_exact_1.numpy()
    snapshots["u_analytical_t0.10"] = u_exact_2.numpy()

    np.savez(
        os.path.join(OUTDIR, "ref_3_5.npz"),
        x=x.numpy(),
        y=y.numpy(),
        **snapshots,
    )
    print("  Saved ref_3_5.npz")


def run_all():
    run_ref_3_1()
    run_ref_3_3()
    run_ref_3_4()
    run_ref_3_5()


if __name__ == "__main__":
    run_all()
