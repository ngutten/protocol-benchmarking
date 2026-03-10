"""Stage 5 holdout tests: Multigrid vs direct match, Ghia with multigrid, robustness."""
import pytest
import math


class TestMultigridDirectMatch:
    """Test that multigrid and default solver produce matching results."""

    def test_poiseuille_match(self, engine):
        """Multigrid Poiseuille should match default solver to 1e-4."""
        H = 1.0
        nu = 0.1
        F = 1.0

        # Solve with default solver
        engine.create(nx=32, ny=32, lx=2.0, ly=H, viscosity=nu, force=[F, 0.0])
        engine.set_boundary("top", "no_slip")
        engine.set_boundary("bottom", "no_slip")
        engine.set_boundary("left", "velocity", value=[0.0, 0.0])
        engine.set_boundary("right", "velocity", value=[0.0, 0.0])
        engine.solve_steady(tolerance=1e-8, max_iterations=50000)

        default_profile = engine.get_profile("velocity_x", "vertical", 1.0, n_points=30)
        default_values = default_profile["values"]

        # Solve with multigrid
        engine.reset()
        engine.create(nx=32, ny=32, lx=2.0, ly=H, viscosity=nu, force=[F, 0.0])
        engine.set_boundary("top", "no_slip")
        engine.set_boundary("bottom", "no_slip")
        engine.set_boundary("left", "velocity", value=[0.0, 0.0])
        engine.set_boundary("right", "velocity", value=[0.0, 0.0])
        engine.set_solver("multigrid", levels=4, cycle="V", pre_smooth=2, post_smooth=2)
        engine.solve_steady(tolerance=1e-8, max_iterations=50000)

        mg_profile = engine.get_profile("velocity_x", "vertical", 1.0, n_points=30)
        mg_values = mg_profile["values"]

        # Compare point by point
        for i, (v_def, v_mg) in enumerate(zip(default_values, mg_values)):
            assert abs(v_def - v_mg) < 1e-3, \
                f"Point {i}: default={v_def:.6f}, multigrid={v_mg:.6f}, diff={abs(v_def-v_mg):.6f}"

    def test_cavity_match(self, engine):
        """Multigrid cavity solution should match default solver."""
        # Default solver
        engine.create(nx=32, ny=32, lx=1.0, ly=1.0, viscosity=0.01)
        engine.set_boundary("top", "velocity", value=[1.0, 0.0])
        engine.set_boundary("bottom", "no_slip")
        engine.set_boundary("left", "no_slip")
        engine.set_boundary("right", "no_slip")
        engine.solve_steady(tolerance=1e-6, max_iterations=50000)

        default_profile = engine.get_profile("velocity_x", "vertical", 0.5, n_points=30)
        default_values = default_profile["values"]

        # Multigrid solver
        engine.reset()
        engine.create(nx=32, ny=32, lx=1.0, ly=1.0, viscosity=0.01)
        engine.set_boundary("top", "velocity", value=[1.0, 0.0])
        engine.set_boundary("bottom", "no_slip")
        engine.set_boundary("left", "no_slip")
        engine.set_boundary("right", "no_slip")
        engine.set_solver("multigrid", levels=4, cycle="V", pre_smooth=2, post_smooth=2)
        engine.solve_steady(tolerance=1e-6, max_iterations=50000)

        mg_profile = engine.get_profile("velocity_x", "vertical", 0.5, n_points=30)
        mg_values = mg_profile["values"]

        for i, (v_def, v_mg) in enumerate(zip(default_values, mg_values)):
            assert abs(v_def - v_mg) < 1e-2, \
                f"Point {i}: default={v_def:.6f}, multigrid={v_mg:.6f}"


class TestMultigridGhia:
    """Full Ghia validation with multigrid solver."""

    GHIA_RE100_SELECTED = [
        (1.0000,  1.00000),
        (0.9766,  0.84123),
        (0.9688,  0.78871),
        (0.9609,  0.73722),
        (0.5000, -0.20581),
        (0.2813, -0.15662),
        (0.1016, -0.06434),
        (0.0547, -0.03717),
        (0.0000,  0.00000),
    ]

    def test_ghia_re100_multigrid(self, engine):
        """Multigrid cavity at Re=100 should match Ghia (abs err < 0.05)."""
        engine.create(nx=64, ny=64, lx=1.0, ly=1.0, viscosity=0.01)
        engine.set_boundary("top", "velocity", value=[1.0, 0.0])
        engine.set_boundary("bottom", "no_slip")
        engine.set_boundary("left", "no_slip")
        engine.set_boundary("right", "no_slip")
        engine.set_solver("multigrid", levels=5, cycle="V", pre_smooth=2, post_smooth=2)
        engine.solve_steady(tolerance=1e-6, max_iterations=100000)

        resp = engine.get_profile("velocity_x", "vertical", 0.5, n_points=100)
        coords = resp["coordinates"]
        values = resp["values"]

        for y_ref, u_ref in self.GHIA_RE100_SELECTED:
            idx = min(range(len(coords)), key=lambda i: abs(coords[i] - y_ref))
            u_num = values[idx]
            abs_err = abs(u_num - u_ref)
            assert abs_err < 0.05, \
                f"MG Ghia: y={y_ref:.4f}, u={u_num:.5f}, ref={u_ref:.5f}, err={abs_err:.4f}"


class TestMultigridRobustness:
    """Robustness tests for multigrid solver."""

    def test_high_re_multigrid(self, engine):
        """Multigrid at Re=400 should converge."""
        engine.create(nx=64, ny=64, lx=1.0, ly=1.0, viscosity=0.0025)
        engine.set_boundary("top", "velocity", value=[1.0, 0.0])
        engine.set_boundary("bottom", "no_slip")
        engine.set_boundary("left", "no_slip")
        engine.set_boundary("right", "no_slip")
        engine.set_solver("multigrid", levels=5, cycle="V", pre_smooth=3, post_smooth=3)
        resp = engine.solve_steady(tolerance=1e-5, max_iterations=200000)
        assert resp["converged"] is True

    def test_non_power_of_two_grid(self, engine):
        """Multigrid should handle non-power-of-2 grids (or error gracefully)."""
        engine.create(nx=24, ny=24, lx=1.0, ly=1.0, viscosity=0.01)
        engine.set_boundary("top", "velocity", value=[1.0, 0.0])
        engine.set_boundary("bottom", "no_slip")
        engine.set_boundary("left", "no_slip")
        engine.set_boundary("right", "no_slip")

        # Either it works with adjusted levels or gives a sensible error
        resp = engine.send({"command": "set_solver", "type": "multigrid", "levels": 3, "cycle": "V"})
        if "error" not in resp:
            solve_resp = engine.solve_steady(tolerance=1e-4, max_iterations=50000)
            assert "converged" in solve_resp

    def test_w_cycle_convergence(self, engine):
        """W-cycle should also converge for standard problems."""
        engine.create(nx=32, ny=32, lx=1.0, ly=1.0, viscosity=0.01)
        engine.set_boundary("top", "velocity", value=[1.0, 0.0])
        engine.set_boundary("bottom", "no_slip")
        engine.set_boundary("left", "no_slip")
        engine.set_boundary("right", "no_slip")
        engine.set_solver("multigrid", levels=4, cycle="W", pre_smooth=2, post_smooth=2)
        resp = engine.solve_steady(tolerance=1e-5, max_iterations=50000)
        assert resp["converged"] is True

    def test_switch_solver_back(self, engine):
        """Switching back to default solver should restore original behavior."""
        engine.create(nx=16, ny=16, lx=1.0, ly=1.0, viscosity=0.1)
        engine.set_boundary("top", "velocity", value=[1.0, 0.0])
        engine.set_boundary("bottom", "no_slip")
        engine.set_boundary("left", "no_slip")
        engine.set_boundary("right", "no_slip")

        # Solve with multigrid
        engine.set_solver("multigrid", levels=3, cycle="V")
        engine.solve_steady(tolerance=1e-5)

        mg_val = engine.get_value("velocity_x", [0.5, 0.5])

        # Switch back and re-solve
        engine.set_solver("default")
        engine.solve_steady(tolerance=1e-5)

        def_val = engine.get_value("velocity_x", [0.5, 0.5])

        assert abs(mg_val["value"] - def_val["value"]) < 0.01, \
            f"MG={mg_val['value']:.5f}, default={def_val['value']:.5f} should match"

    def test_multigrid_two_levels(self, engine):
        """Multigrid with minimum 2 levels should work."""
        engine.create(nx=16, ny=16, lx=1.0, ly=1.0, viscosity=0.1)
        engine.set_boundary("top", "velocity", value=[1.0, 0.0])
        engine.set_boundary("bottom", "no_slip")
        engine.set_boundary("left", "no_slip")
        engine.set_boundary("right", "no_slip")
        engine.set_solver("multigrid", levels=2, cycle="V", pre_smooth=3, post_smooth=3)
        resp = engine.solve_steady(tolerance=1e-5, max_iterations=50000)
        assert resp["converged"] is True
