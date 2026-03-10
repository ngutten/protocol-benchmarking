"""Stage 5 training tests: Multigrid solver API and equivalence with default solver."""
import pytest
import math


class TestSetSolver:
    """Test the set_solver command."""

    def test_set_solver_multigrid(self, engine):
        engine.create(nx=32, ny=32, lx=1.0, ly=1.0, viscosity=0.01)
        resp = engine.set_solver("multigrid", levels=4, cycle="V", pre_smooth=2, post_smooth=2)
        assert resp["status"] == "ok"

    def test_set_solver_default(self, engine):
        engine.create(nx=32, ny=32, lx=1.0, ly=1.0, viscosity=0.01)
        engine.set_solver("multigrid", levels=4, cycle="V")
        resp = engine.set_solver("default")
        assert resp["status"] == "ok"

    def test_set_solver_before_create(self, engine):
        engine.expect_error(
            {"command": "set_solver", "type": "multigrid", "levels": 4, "cycle": "V"},
            "No simulation"
        )

    def test_invalid_cycle_type(self, engine):
        engine.create(nx=32, ny=32, lx=1.0, ly=1.0, viscosity=0.01)
        engine.expect_error(
            {"command": "set_solver", "type": "multigrid", "levels": 4, "cycle": "X"},
            "Invalid cycle"
        )

    def test_w_cycle(self, engine):
        engine.create(nx=32, ny=32, lx=1.0, ly=1.0, viscosity=0.01)
        resp = engine.set_solver("multigrid", levels=3, cycle="W", pre_smooth=3, post_smooth=3)
        assert resp["status"] == "ok"


class TestMultigridPoiseuille:
    """Test that multigrid produces same Poiseuille solution as default solver."""

    def test_poiseuille_multigrid(self, engine):
        """Poiseuille flow with multigrid should match analytical solution."""
        H = 1.0
        nu = 0.1
        F = 1.0
        engine.create(nx=32, ny=32, lx=2.0, ly=H, viscosity=nu, force=[F, 0.0])
        engine.set_boundary("top", "no_slip")
        engine.set_boundary("bottom", "no_slip")
        engine.set_boundary("left", "velocity", value=[0.0, 0.0])
        engine.set_boundary("right", "velocity", value=[0.0, 0.0])
        engine.set_solver("multigrid", levels=4, cycle="V", pre_smooth=2, post_smooth=2)
        resp = engine.solve_steady(tolerance=1e-6, max_iterations=50000)
        assert resp["converged"] is True

        resp = engine.get_profile("velocity_x", "vertical", 1.0, n_points=20)
        coords = resp["coordinates"]
        values = resp["values"]

        for y, u_num in zip(coords, values):
            u_exact = (F / (2.0 * nu)) * y * (H - y)
            if u_exact > 1e-10:
                rel_err = abs(u_num - u_exact) / u_exact
                assert rel_err < 1e-2, \
                    f"Multigrid Poiseuille: at y={y:.3f}, rel_err={rel_err:.4f}"


class TestMultigridCavity:
    """Test lid-driven cavity with multigrid matches default solver."""

    def test_cavity_multigrid_convergence(self, engine):
        """Multigrid solver should converge for lid-driven cavity at Re=100."""
        engine.create(nx=32, ny=32, lx=1.0, ly=1.0, viscosity=0.01)
        engine.set_boundary("top", "velocity", value=[1.0, 0.0])
        engine.set_boundary("bottom", "no_slip")
        engine.set_boundary("left", "no_slip")
        engine.set_boundary("right", "no_slip")
        engine.set_solver("multigrid", levels=4, cycle="V", pre_smooth=2, post_smooth=2)
        resp = engine.solve_steady(tolerance=1e-5, max_iterations=50000)
        assert resp["converged"] is True

    def test_cavity_multigrid_matches_ghia(self, engine):
        """Multigrid cavity solution should match Ghia reference data."""
        # Selected Ghia Re=100 points
        ghia_points = [
            (1.0000, 1.00000),
            (0.5000, -0.06080),
            (0.0000, 0.00000),
        ]

        engine.create(nx=32, ny=32, lx=1.0, ly=1.0, viscosity=0.01)
        engine.set_boundary("top", "velocity", value=[1.0, 0.0])
        engine.set_boundary("bottom", "no_slip")
        engine.set_boundary("left", "no_slip")
        engine.set_boundary("right", "no_slip")
        engine.set_solver("multigrid", levels=4, cycle="V", pre_smooth=2, post_smooth=2)
        engine.solve_steady(tolerance=1e-6, max_iterations=50000)

        resp = engine.get_profile("velocity_x", "vertical", 0.5, n_points=50)
        coords = resp["coordinates"]
        values = resp["values"]

        for y_ref, u_ref in ghia_points:
            idx = min(range(len(coords)), key=lambda i: abs(coords[i] - y_ref))
            u_num = values[idx]
            abs_err = abs(u_num - u_ref)
            assert abs_err < 0.05, \
                f"Multigrid Ghia: at y={y_ref:.4f}, u_num={u_num:.5f}, u_ref={u_ref:.5f}, err={abs_err:.4f}"


class TestMultigridTimeStepping:
    """Test that multigrid works with time-stepping."""

    def test_step_with_multigrid(self, engine):
        engine.create(nx=16, ny=16, lx=1.0, ly=1.0, viscosity=0.01)
        engine.set_boundary("top", "velocity", value=[1.0, 0.0])
        engine.set_boundary("bottom", "no_slip")
        engine.set_boundary("left", "no_slip")
        engine.set_boundary("right", "no_slip")
        engine.set_solver("multigrid", levels=3, cycle="V", pre_smooth=2, post_smooth=2)
        resp = engine.step(dt=0.01, steps=5)
        assert resp["steps_completed"] == 5
        assert resp["time"] == pytest.approx(0.05, abs=1e-10)
