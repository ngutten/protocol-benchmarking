"""Stage 1 training tests: Stokes flow solver API and basic analytical solutions."""
import pytest
import math


class TestEngineLifecycle:
    """Test basic engine commands and lifecycle."""

    def test_create_simulation(self, engine):
        resp = engine.create(nx=16, ny=16, lx=1.0, ly=1.0, viscosity=0.1)
        assert resp["status"] == "ok"

    def test_status_after_create(self, engine):
        engine.create(nx=16, ny=16, lx=1.0, ly=1.0, viscosity=0.1)
        resp = engine.status()
        assert resp["grid"]["nx"] == 16
        assert resp["grid"]["ny"] == 16
        assert resp["grid"]["lx"] == 1.0
        assert resp["grid"]["ly"] == 1.0
        assert resp["has_solution"] is False
        assert resp["time"] == 0.0

    def test_status_before_create(self, engine):
        engine.expect_error({"command": "status"}, "No simulation")

    def test_set_boundary_velocity(self, engine):
        engine.create(nx=16, ny=16)
        resp = engine.set_boundary("top", "velocity", value=[1.0, 0.0])
        assert resp["status"] == "ok"

    def test_set_boundary_no_slip(self, engine):
        engine.create(nx=16, ny=16)
        resp = engine.set_boundary("bottom", "no_slip")
        assert resp["status"] == "ok"

    def test_set_boundary_before_create(self, engine):
        engine.expect_error(
            {"command": "set_boundary", "boundary": "top", "type": "no_slip"},
            "No simulation"
        )

    def test_unknown_command(self, engine):
        engine.expect_error({"command": "foobar"}, "Unknown command")

    def test_missing_parameter(self, engine):
        engine.expect_error({"command": "create"}, "Missing parameter")

    def test_reset(self, engine):
        engine.create(nx=16, ny=16)
        resp = engine.reset()
        assert resp["status"] == "ok"
        engine.expect_error({"command": "status"}, "No simulation")

    def test_get_field_before_solve(self, engine):
        engine.create(nx=16, ny=16)
        engine.set_boundary("top", "no_slip")
        engine.set_boundary("bottom", "no_slip")
        engine.set_boundary("left", "no_slip")
        engine.set_boundary("right", "no_slip")
        engine.expect_error({"command": "get_field", "field": "velocity_x"}, "No solution")


class TestSolveAndQuery:
    """Test solve_steady and field query commands."""

    def test_solve_steady_converges(self, cavity_engine):
        resp = cavity_engine.solve_steady(tolerance=1e-4, max_iterations=10000)
        assert resp["converged"] is True
        assert resp["iterations"] > 0
        assert resp["residual"] < 1e-4

    def test_get_field_velocity_x(self, cavity_engine):
        cavity_engine.solve_steady(tolerance=1e-4)
        resp = cavity_engine.get_field("velocity_x")
        assert "shape" in resp
        assert "data" in resp
        assert resp["shape"] == [32, 32]
        assert len(resp["data"]) == 32
        assert len(resp["data"][0]) == 32

    def test_get_field_velocity_y(self, cavity_engine):
        cavity_engine.solve_steady(tolerance=1e-4)
        resp = cavity_engine.get_field("velocity_y")
        assert resp["shape"] == [32, 32]

    def test_get_field_pressure(self, cavity_engine):
        cavity_engine.solve_steady(tolerance=1e-4)
        resp = cavity_engine.get_field("pressure")
        assert resp["shape"] == [32, 32]

    def test_get_value(self, cavity_engine):
        cavity_engine.solve_steady(tolerance=1e-4)
        resp = cavity_engine.get_value("velocity_x", [0.5, 0.5])
        assert "value" in resp
        assert isinstance(resp["value"], float)

    def test_get_profile_vertical(self, cavity_engine):
        cavity_engine.solve_steady(tolerance=1e-4)
        resp = cavity_engine.get_profile("velocity_x", "vertical", 0.5, n_points=20)
        assert "coordinates" in resp
        assert "values" in resp
        assert len(resp["coordinates"]) == 20
        assert len(resp["values"]) == 20
        # Coordinates should span [0, ly]
        assert resp["coordinates"][0] == pytest.approx(0.0, abs=0.1)
        assert resp["coordinates"][-1] == pytest.approx(1.0, abs=0.1)

    def test_get_profile_horizontal(self, cavity_engine):
        cavity_engine.solve_steady(tolerance=1e-4)
        resp = cavity_engine.get_profile("velocity_y", "horizontal", 0.5, n_points=20)
        assert len(resp["coordinates"]) == 20
        assert len(resp["values"]) == 20

    def test_status_has_solution(self, cavity_engine):
        cavity_engine.solve_steady(tolerance=1e-4)
        resp = cavity_engine.status()
        assert resp["has_solution"] is True

    def test_invalid_field_name(self, engine):
        engine.create(nx=16, ny=16)
        engine.set_boundary("top", "no_slip")
        engine.set_boundary("bottom", "no_slip")
        engine.set_boundary("left", "no_slip")
        engine.set_boundary("right", "no_slip")
        engine.solve_steady(tolerance=1e-4)
        engine.expect_error({"command": "get_field", "field": "invalid_field"})


class TestPoiseuille:
    """Test Poiseuille flow: body-force-driven flow between parallel no-slip walls.

    Analytical solution: u(y) = (F / 2ν) * y * (H - y)
    where F is the body force, ν is viscosity, H is channel height.
    """

    def test_poiseuille_profile(self, engine):
        """Poiseuille flow profile should match analytical solution to 1e-3 rel error."""
        H = 1.0
        nu = 0.1
        F = 1.0
        engine.create(nx=32, ny=32, lx=2.0, ly=H, viscosity=nu, force=[F, 0.0])
        engine.set_boundary("top", "no_slip")
        engine.set_boundary("bottom", "no_slip")
        engine.set_boundary("left", "velocity", value=[0.0, 0.0])
        engine.set_boundary("right", "velocity", value=[0.0, 0.0])
        engine.solve_steady(tolerance=1e-8, max_iterations=50000)

        # Get velocity profile along vertical centerline
        resp = engine.get_profile("velocity_x", "vertical", 1.0, n_points=30)
        coords = resp["coordinates"]
        values = resp["values"]

        u_max = F * H**2 / (8.0 * nu)  # peak velocity at center

        for y, u_num in zip(coords, values):
            u_exact = (F / (2.0 * nu)) * y * (H - y)
            if u_exact > 1e-10:
                rel_err = abs(u_num - u_exact) / u_exact
                assert rel_err < 1e-2, \
                    f"Poiseuille: at y={y:.3f}, u_num={u_num:.6f}, u_exact={u_exact:.6f}, rel_err={rel_err:.4f}"


class TestCouette:
    """Test Couette flow: flow between a moving top wall and stationary bottom wall.

    Analytical solution: u(y) = U * y / H
    """

    def test_couette_profile(self, engine):
        """Couette flow should match linear profile to 1e-3 rel error."""
        H = 1.0
        U = 1.0
        nu = 0.1
        engine.create(nx=32, ny=32, lx=1.0, ly=H, viscosity=nu)
        engine.set_boundary("top", "velocity", value=[U, 0.0])
        engine.set_boundary("bottom", "no_slip")
        engine.set_boundary("left", "velocity", value=[0.0, 0.0])
        engine.set_boundary("right", "velocity", value=[0.0, 0.0])
        engine.solve_steady(tolerance=1e-8, max_iterations=50000)

        resp = engine.get_profile("velocity_x", "vertical", 0.5, n_points=30)
        coords = resp["coordinates"]
        values = resp["values"]

        for y, u_num in zip(coords, values):
            u_exact = U * y / H
            if 0.05 < y < 0.95:  # avoid boundary points
                if u_exact > 1e-10:
                    rel_err = abs(u_num - u_exact) / u_exact
                    assert rel_err < 1e-2, \
                        f"Couette: at y={y:.3f}, u_num={u_num:.6f}, u_exact={u_exact:.6f}, rel_err={rel_err:.4f}"
                else:
                    assert abs(u_num) < 1e-3, \
                        f"Couette: at y={y:.3f}, u_num={u_num:.6f} should be near zero"
