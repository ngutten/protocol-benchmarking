"""
Holdout tests for Stage 1: Diffusion equation solver.

These tests cover edge cases, validation, and alternative scenarios not
present in the training tests. They verify the solver handles non-standard
grids, boundary condition combinations, symmetry preservation, and
API consistency.
"""

import numpy as np
import pytest

import pdesolver
from conftest import l2_error, max_error


# ---------------------------------------------------------------------------
# 1. Different Grid Sizes (non-square grids)
# ---------------------------------------------------------------------------


class TestDifferentGridSizes:
    """Verify the solver handles rectangular (non-square) grids correctly."""

    @pytest.mark.parametrize("nx,ny", [(51, 101), (201, 51), (31, 81)])
    def test_rectangular_grid_diffusion(self, sim_factory, nx, ny):
        """Diffusion on a rectangular grid matches the analytical solution."""
        s = sim_factory(x_range=(0, 1), y_range=(0, 1), nx=nx, ny=ny)
        s.add_field("u", D=1.0)
        s.set_initial_condition(
            "u", lambda x, y: np.sin(np.pi * x) * np.sin(np.pi * y)
        )
        s.set_bc("u", "all", "dirichlet", value=0.0)

        t_final = 0.02
        dx = 1.0 / (nx - 1)
        dy = 1.0 / (ny - 1)
        dt = min(0.25 * dx ** 2, 0.25 * dy ** 2)
        s.run_until(t_final, dt=dt)

        u = s.get_field("u")
        x, y = s.coordinates()
        X, Y = np.meshgrid(x, y, indexing="ij")
        u_analytical = (
            np.sin(np.pi * X) * np.sin(np.pi * Y)
            * np.exp(-2 * np.pi ** 2 * t_final)
        )

        ref_norm = np.sqrt(np.mean(u_analytical ** 2))
        rel_err = l2_error(u, u_analytical) / ref_norm
        assert rel_err < 0.20, (
            f"Relative L2 error on {nx}x{ny} grid: {rel_err:.4e}"
        )

    @pytest.mark.parametrize("nx,ny", [(51, 101), (201, 51)])
    def test_field_shape_matches_grid(self, sim_factory, nx, ny):
        """get_field returns an array whose shape matches the grid dimensions."""
        s = sim_factory(x_range=(0, 1), y_range=(0, 1), nx=nx, ny=ny)
        s.add_field("u", D=1.0)
        s.set_initial_condition("u", lambda x, y: np.zeros_like(x))
        s.set_bc("u", "all", "dirichlet", value=0.0)

        u = s.get_field("u")
        assert u.shape == (nx, ny), (
            f"Expected shape ({nx}, {ny}), got {u.shape}"
        )


# ---------------------------------------------------------------------------
# 2. Different Domain Sizes (non-square domains)
# ---------------------------------------------------------------------------


class TestDifferentDomainSizes:
    """Verify the solver handles non-square physical domains."""

    def test_tall_domain(self, sim_factory):
        """Diffusion on a [0,5]x[0,20] domain produces correct results."""
        Lx, Ly = 5.0, 20.0
        nx, ny = 51, 101
        s = sim_factory(x_range=(0, Lx), y_range=(0, Ly), nx=nx, ny=ny)
        s.add_field("u", D=1.0)
        s.set_initial_condition(
            "u",
            lambda x, y: np.sin(np.pi * x / Lx) * np.sin(np.pi * y / Ly),
        )
        s.set_bc("u", "all", "dirichlet", value=0.0)

        t_final = 0.1
        dx = Lx / (nx - 1)
        dy = Ly / (ny - 1)
        dt = min(0.2 * dx ** 2, 0.2 * dy ** 2)
        s.run_until(t_final, dt=dt)

        u = s.get_field("u")
        x, y = s.coordinates()
        X, Y = np.meshgrid(x, y, indexing="ij")
        decay = np.pi ** 2 * ((1.0 / Lx) ** 2 + (1.0 / Ly) ** 2)
        u_analytical = (
            np.sin(np.pi * X / Lx) * np.sin(np.pi * Y / Ly)
            * np.exp(-decay * t_final)
        )

        ref_norm = np.sqrt(np.mean(u_analytical ** 2))
        rel_err = l2_error(u, u_analytical) / ref_norm
        assert rel_err < 0.20, (
            f"Relative L2 error on tall domain: {rel_err:.4e}"
        )

    def test_wide_domain(self, sim_factory):
        """Diffusion on a [0,20]x[0,3] domain produces correct results."""
        Lx, Ly = 20.0, 3.0
        nx, ny = 101, 31
        s = sim_factory(x_range=(0, Lx), y_range=(0, Ly), nx=nx, ny=ny)
        s.add_field("u", D=0.5)
        s.set_initial_condition(
            "u",
            lambda x, y: np.sin(np.pi * x / Lx) * np.sin(np.pi * y / Ly),
        )
        s.set_bc("u", "all", "dirichlet", value=0.0)

        D = 0.5
        t_final = 0.5
        dx = Lx / (nx - 1)
        dy = Ly / (ny - 1)
        dt = min(0.2 * dx ** 2 / D, 0.2 * dy ** 2 / D)
        s.run_until(t_final, dt=dt)

        u = s.get_field("u")
        x, y = s.coordinates()
        X, Y = np.meshgrid(x, y, indexing="ij")
        decay = D * np.pi ** 2 * ((1.0 / Lx) ** 2 + (1.0 / Ly) ** 2)
        u_analytical = (
            np.sin(np.pi * X / Lx) * np.sin(np.pi * Y / Ly)
            * np.exp(-decay * t_final)
        )

        ref_norm = np.sqrt(np.mean(u_analytical ** 2))
        rel_err = l2_error(u, u_analytical) / ref_norm
        assert rel_err < 0.20, (
            f"Relative L2 error on wide domain: {rel_err:.4e}"
        )


# ---------------------------------------------------------------------------
# 3. Small Grid
# ---------------------------------------------------------------------------


class TestSmallGrid:
    """Verify the solver works with a minimal grid, possibly at reduced accuracy."""

    def test_small_grid_runs(self, sim_factory):
        """An 11x11 grid should still produce a valid (no NaN) solution."""
        s = sim_factory(x_range=(0, 1), y_range=(0, 1), nx=11, ny=11)
        s.add_field("u", D=1.0)
        s.set_initial_condition(
            "u", lambda x, y: np.sin(np.pi * x) * np.sin(np.pi * y)
        )
        s.set_bc("u", "all", "dirichlet", value=0.0)

        dt = 0.25 * (0.1 ** 2)  # dx = 0.1
        s.run_until(0.01, dt=dt)

        u = s.get_field("u")
        assert not np.any(np.isnan(u)), "Solution contains NaN on small grid"
        assert not np.any(np.isinf(u)), "Solution contains Inf on small grid"

    def test_small_grid_qualitative_accuracy(self, sim_factory):
        """11x11 grid solution should be within 20% of the analytical answer."""
        s = sim_factory(x_range=(0, 1), y_range=(0, 1), nx=11, ny=11)
        s.add_field("u", D=1.0)
        s.set_initial_condition(
            "u", lambda x, y: np.sin(np.pi * x) * np.sin(np.pi * y)
        )
        s.set_bc("u", "all", "dirichlet", value=0.0)

        t_final = 0.02
        dt = 0.2 * (0.1 ** 2)
        s.run_until(t_final, dt=dt)

        u = s.get_field("u")
        x, y = s.coordinates()
        X, Y = np.meshgrid(x, y, indexing="ij")
        u_analytical = (
            np.sin(np.pi * X) * np.sin(np.pi * Y)
            * np.exp(-2 * np.pi ** 2 * t_final)
        )

        ref_norm = np.sqrt(np.mean(u_analytical ** 2))
        rel_err = l2_error(u, u_analytical) / ref_norm
        # Looser tolerance for coarse grid
        assert rel_err < 0.20, (
            f"Small grid relative L2 error: {rel_err:.4e} (limit 20%)"
        )


# ---------------------------------------------------------------------------
# 4. Mixed Boundary Conditions
# ---------------------------------------------------------------------------


class TestMixedBoundaryConditions:
    """
    Different BC types on different edges: Dirichlet on top/bottom,
    Neumann (zero flux) on left/right.
    """

    def test_mixed_bc_no_nan(self, sim_factory):
        """Mixed BCs produce a valid solution without NaN or Inf."""
        s = sim_factory(x_range=(0, 1), y_range=(0, 1), nx=51, ny=51)
        s.add_field("u", D=1.0)
        s.set_initial_condition("u", lambda x, y: np.ones_like(x))
        s.set_bc("u", "top", "dirichlet", value=0.0)
        s.set_bc("u", "bottom", "dirichlet", value=0.0)
        s.set_bc("u", "left", "neumann", flux=0.0)
        s.set_bc("u", "right", "neumann", flux=0.0)

        s.run_until(0.05, dt=1e-4)
        u = s.get_field("u")

        assert not np.any(np.isnan(u)), "Solution contains NaN"
        assert not np.any(np.isinf(u)), "Solution contains Inf"

    def test_mixed_bc_bounded(self, sim_factory):
        """With IC=1 and Dirichlet=0 on top/bottom, solution stays in [0, 1]."""
        s = sim_factory(x_range=(0, 1), y_range=(0, 1), nx=51, ny=51)
        s.add_field("u", D=1.0)
        s.set_initial_condition("u", lambda x, y: np.ones_like(x))
        s.set_bc("u", "top", "dirichlet", value=0.0)
        s.set_bc("u", "bottom", "dirichlet", value=0.0)
        s.set_bc("u", "left", "neumann", flux=0.0)
        s.set_bc("u", "right", "neumann", flux=0.0)

        s.run_until(0.05, dt=1e-4)
        u = s.get_field("u")

        assert np.all(u >= -0.01), f"Solution below 0: min={np.min(u):.4e}"
        assert np.all(u <= 1.0 + 0.01), f"Solution above 1: max={np.max(u):.4e}"

    def test_mixed_bc_energy_decreases(self, sim_factory):
        """Energy should not increase with Dirichlet=0 on some edges."""
        s = sim_factory(x_range=(0, 1), y_range=(0, 1), nx=51, ny=51)
        s.add_field("u", D=1.0)
        s.set_initial_condition("u", lambda x, y: np.ones_like(x))
        s.set_bc("u", "top", "dirichlet", value=0.0)
        s.set_bc("u", "bottom", "dirichlet", value=0.0)
        s.set_bc("u", "left", "neumann", flux=0.0)
        s.set_bc("u", "right", "neumann", flux=0.0)

        x, y = s.coordinates()
        dx = x[1] - x[0]
        dy = y[1] - y[0]

        def energy():
            u = s.get_field("u")
            return np.trapezoid(np.trapezoid(u ** 2, dx=dx, axis=0), dx=dy)

        e0 = energy()
        s.run_until(0.02, dt=1e-4)
        e1 = energy()
        s.run_until(0.05, dt=1e-4)
        e2 = energy()

        assert e1 < e0 + 0.01, f"Energy increased: {e0:.6e} -> {e1:.6e}"
        assert e2 < e1 + 0.01, f"Energy increased: {e1:.6e} -> {e2:.6e}"


# ---------------------------------------------------------------------------
# 5. Zero Diffusion
# ---------------------------------------------------------------------------


class TestZeroDiffusion:
    """With D=0 the field should remain constant (no diffusion)."""

    def test_zero_diffusion_preserves_ic(self, sim_factory):
        """D=0 keeps the field identical to the initial condition."""
        s = sim_factory(x_range=(0, 1), y_range=(0, 1), nx=51, ny=51)
        s.add_field("u", D=0.0)
        s.set_initial_condition(
            "u", lambda x, y: np.sin(np.pi * x) * np.sin(np.pi * y)
        )
        s.set_bc("u", "all", "dirichlet", value=0.0)

        u0 = s.get_field("u").copy()
        s.run_until(0.1, dt=0.001)
        u1 = s.get_field("u")

        err = max_error(u1, u0)
        assert err < 1e-6, (
            f"Field changed with D=0: max deviation = {err:.4e}"
        )

    def test_zero_diffusion_complex_ic(self, sim_factory):
        """D=0 preserves a more complex initial condition."""
        s = sim_factory(x_range=(0, 2), y_range=(0, 2), nx=41, ny=41)
        s.add_field("u", D=0.0)
        s.set_initial_condition(
            "u",
            lambda x, y: np.exp(-((x - 1) ** 2 + (y - 1) ** 2) / 0.2),
        )
        s.set_bc("u", "all", "neumann", flux=0.0)

        u0 = s.get_field("u").copy()
        s.step(dt=0.01, n_steps=50)
        u1 = s.get_field("u")

        err = max_error(u1, u0)
        assert err < 1e-6, (
            f"Field changed with D=0: max deviation = {err:.4e}"
        )


# ---------------------------------------------------------------------------
# 6. Very Small Timestep
# ---------------------------------------------------------------------------


class TestVerySmallTimestep:
    """A very small dt (well below stability limit) should still give correct results."""

    def test_small_dt_accuracy(self, sim_factory):
        """dt much smaller than stability limit still converges to analytical solution."""
        s = sim_factory(x_range=(0, 1), y_range=(0, 1), nx=51, ny=51)
        s.add_field("u", D=1.0)
        s.set_initial_condition(
            "u", lambda x, y: np.sin(np.pi * x) * np.sin(np.pi * y)
        )
        s.set_bc("u", "all", "dirichlet", value=0.0)

        t_final = 0.005
        # Stability limit ~ 0.25 * (1/50)^2 = 1e-4; use dt = 1e-6 (100x smaller)
        dt = 1e-6
        s.run_until(t_final, dt=dt)

        u = s.get_field("u")
        x, y = s.coordinates()
        X, Y = np.meshgrid(x, y, indexing="ij")
        u_analytical = (
            np.sin(np.pi * X) * np.sin(np.pi * Y)
            * np.exp(-2 * np.pi ** 2 * t_final)
        )

        ref_norm = np.sqrt(np.mean(u_analytical ** 2))
        rel_err = l2_error(u, u_analytical) / ref_norm
        assert rel_err < 0.20, (
            f"Relative L2 error with very small dt: {rel_err:.4e}"
        )


# ---------------------------------------------------------------------------
# 7. Symmetry Preservation
# ---------------------------------------------------------------------------


class TestSymmetry:
    """A symmetric IC with symmetric BCs should produce a symmetric field."""

    def test_xy_symmetry(self, sim_factory):
        """IC symmetric in x<->y stays symmetric after many steps."""
        s = sim_factory(x_range=(0, 1), y_range=(0, 1), nx=51, ny=51)
        s.add_field("u", D=1.0)
        # Symmetric IC: f(x,y) = f(y,x)
        s.set_initial_condition(
            "u",
            lambda x, y: np.exp(-((x - 0.5) ** 2 + (y - 0.5) ** 2) / 0.05),
        )
        s.set_bc("u", "all", "dirichlet", value=0.0)

        s.run_until(0.01, dt=1e-5)
        u = s.get_field("u")

        # u should equal its transpose
        err = max_error(u, u.T)
        assert err < 1e-4, (
            f"x<->y symmetry broken: max deviation = {err:.4e}"
        )

    def test_left_right_symmetry(self, sim_factory):
        """IC symmetric about x=0.5 preserves left-right symmetry."""
        s = sim_factory(x_range=(0, 1), y_range=(0, 1), nx=51, ny=51)
        s.add_field("u", D=1.0)
        s.set_initial_condition(
            "u",
            lambda x, y: np.exp(-((x - 0.5) ** 2) / 0.02) * np.sin(np.pi * y),
        )
        s.set_bc("u", "all", "dirichlet", value=0.0)

        s.run_until(0.02, dt=1e-5)
        u = s.get_field("u")

        # u[:, j] should be symmetric about the middle index in the x direction
        u_flipped = u[::-1, :]
        err = max_error(u, u_flipped)
        assert err < 1e-4, (
            f"Left-right symmetry broken: max deviation = {err:.4e}"
        )


# ---------------------------------------------------------------------------
# 8. Step Equivalence
# ---------------------------------------------------------------------------


class TestStepEquivalence:
    """
    Running step(dt, n_steps=N) should give the same result as calling
    step(dt) N times, and the same as run_until(N*dt, dt).
    """

    def _make_sim(self, sim_factory):
        s = sim_factory(x_range=(0, 1), y_range=(0, 1), nx=51, ny=51)
        s.add_field("u", D=1.0)
        s.set_initial_condition(
            "u", lambda x, y: np.sin(np.pi * x) * np.sin(np.pi * y)
        )
        s.set_bc("u", "all", "dirichlet", value=0.0)
        return s

    def test_nsteps_vs_loop(self, sim_factory):
        """step(dt, n_steps=100) equals calling step(dt) 100 times."""
        dt = 1e-5
        N = 100

        # Method A: n_steps
        sim_a = self._make_sim(sim_factory)
        sim_a.step(dt=dt, n_steps=N)
        u_a = sim_a.get_field("u")

        # Method B: loop
        sim_b = self._make_sim(sim_factory)
        for _ in range(N):
            sim_b.step(dt=dt)
        u_b = sim_b.get_field("u")

        err = max_error(u_a, u_b)
        assert err < 1e-6, (
            f"n_steps vs loop mismatch: max error = {err:.4e}"
        )

    def test_nsteps_vs_run_until(self, sim_factory):
        """step(dt, n_steps=100) equals run_until(100*dt, dt)."""
        dt = 1e-5
        N = 100

        sim_a = self._make_sim(sim_factory)
        sim_a.step(dt=dt, n_steps=N)
        u_a = sim_a.get_field("u")

        sim_b = self._make_sim(sim_factory)
        sim_b.run_until(N * dt, dt=dt)
        u_b = sim_b.get_field("u")

        err = max_error(u_a, u_b)
        assert err < 1e-6, (
            f"step vs run_until mismatch: max error = {err:.4e}"
        )

    def test_time_tracking_consistent(self, sim_factory):
        """All three methods produce the same simulation time."""
        dt = 1e-5
        N = 100
        expected_time = N * dt

        sim_a = self._make_sim(sim_factory)
        sim_a.step(dt=dt, n_steps=N)

        sim_b = self._make_sim(sim_factory)
        for _ in range(N):
            sim_b.step(dt=dt)

        sim_c = self._make_sim(sim_factory)
        sim_c.run_until(expected_time, dt=dt)

        assert sim_a.time == pytest.approx(expected_time, abs=1e-6)
        assert sim_b.time == pytest.approx(expected_time, abs=1e-6)
        assert sim_c.time == pytest.approx(expected_time, abs=1e-6)


# ---------------------------------------------------------------------------
# 9. Field Access During Simulation
# ---------------------------------------------------------------------------


class TestFieldAccessDuringSimulation:
    """Getting the field at intermediate times should not affect the simulation."""

    def test_intermediate_access_no_side_effect(self, sim_factory):
        """Accessing the field mid-simulation does not alter the final result."""
        dt = 1e-4

        # Run A: access field at intermediate time
        sim_a = sim_factory(x_range=(0, 1), y_range=(0, 1), nx=51, ny=51)
        sim_a.add_field("u", D=1.0)
        sim_a.set_initial_condition(
            "u", lambda x, y: np.sin(np.pi * x) * np.sin(np.pi * y)
        )
        sim_a.set_bc("u", "all", "dirichlet", value=0.0)
        sim_a.run_until(0.005, dt=dt)
        _ = sim_a.get_field("u")  # intermediate read
        sim_a.run_until(0.01, dt=dt)
        u_a = sim_a.get_field("u")

        # Run B: no intermediate access
        sim_b = sim_factory(x_range=(0, 1), y_range=(0, 1), nx=51, ny=51)
        sim_b.add_field("u", D=1.0)
        sim_b.set_initial_condition(
            "u", lambda x, y: np.sin(np.pi * x) * np.sin(np.pi * y)
        )
        sim_b.set_bc("u", "all", "dirichlet", value=0.0)
        sim_b.run_until(0.01, dt=dt)
        u_b = sim_b.get_field("u")

        err = max_error(u_a, u_b)
        assert err < 1e-6, (
            f"Intermediate field access changed result: max error = {err:.4e}"
        )

    def test_field_shows_evolution(self, sim_factory):
        """Getting the field at two different times shows evolution."""
        s = sim_factory(x_range=(0, 1), y_range=(0, 1), nx=51, ny=51)
        s.add_field("u", D=1.0)
        s.set_initial_condition(
            "u", lambda x, y: np.sin(np.pi * x) * np.sin(np.pi * y)
        )
        s.set_bc("u", "all", "dirichlet", value=0.0)

        s.run_until(0.005, dt=1e-4)
        u_early = s.get_field("u").copy()

        s.run_until(0.02, dt=1e-4)
        u_late = s.get_field("u")

        # The peak should have decayed
        assert np.max(u_late) < np.max(u_early), (
            f"Peak did not decay: early={np.max(u_early):.6f}, "
            f"late={np.max(u_late):.6f}"
        )
        # Fields should be different
        diff = np.sqrt(np.mean((u_late - u_early) ** 2))
        assert diff > 1e-6, "Field did not evolve between time snapshots"


# ---------------------------------------------------------------------------
# 10. Negative Initial Condition
# ---------------------------------------------------------------------------


class TestNegativeIC:
    """Diffusion with negative initial values should work correctly."""

    def test_negative_ic_diffusion(self, sim_factory):
        """Negative IC diffuses and decays toward boundary values."""
        s = sim_factory(x_range=(0, 1), y_range=(0, 1), nx=51, ny=51)
        s.add_field("u", D=1.0)
        s.set_initial_condition(
            "u", lambda x, y: -np.sin(np.pi * x) * np.sin(np.pi * y)
        )
        s.set_bc("u", "all", "dirichlet", value=0.0)

        t_final = 0.02
        s.run_until(t_final, dt=1e-5)
        u = s.get_field("u")

        x, y = s.coordinates()
        X, Y = np.meshgrid(x, y, indexing="ij")
        u_analytical = (
            -np.sin(np.pi * X) * np.sin(np.pi * Y)
            * np.exp(-2 * np.pi ** 2 * t_final)
        )

        ref_norm = np.sqrt(np.mean(u_analytical ** 2))
        rel_err = l2_error(u, u_analytical) / ref_norm
        assert rel_err < 0.20, (
            f"Relative L2 error with negative IC: {rel_err:.4e}"
        )

    def test_negative_ic_stays_negative(self, sim_factory):
        """With negative IC and zero Dirichlet BCs, interior stays non-positive."""
        s = sim_factory(x_range=(0, 1), y_range=(0, 1), nx=51, ny=51)
        s.add_field("u", D=1.0)
        s.set_initial_condition(
            "u", lambda x, y: -np.sin(np.pi * x) * np.sin(np.pi * y)
        )
        s.set_bc("u", "all", "dirichlet", value=0.0)

        s.run_until(0.05, dt=1e-5)
        u = s.get_field("u")

        # By the maximum principle, u should stay <= 0 (boundary value)
        assert np.all(u <= 0.01), (
            f"Negative IC produced positive values: max = {np.max(u):.4e}"
        )
