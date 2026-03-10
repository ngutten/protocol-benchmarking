"""Stage 2 training tests: Navier-Stokes time stepping, vorticity, lid-driven cavity."""
import pytest
import math


class TestTimestepping:
    """Test the step command and time-dependent simulation."""

    def test_step_command(self, engine):
        engine.create(nx=16, ny=16, lx=1.0, ly=1.0, viscosity=0.01)
        engine.set_boundary("top", "velocity", value=[1.0, 0.0])
        engine.set_boundary("bottom", "no_slip")
        engine.set_boundary("left", "no_slip")
        engine.set_boundary("right", "no_slip")
        resp = engine.step(dt=0.01, steps=10)
        assert "time" in resp
        assert "steps_completed" in resp
        assert resp["steps_completed"] == 10
        assert resp["time"] == pytest.approx(0.1, abs=1e-10)

    def test_step_accumulates_time(self, engine):
        engine.create(nx=16, ny=16, lx=1.0, ly=1.0, viscosity=0.01)
        engine.set_boundary("top", "velocity", value=[1.0, 0.0])
        engine.set_boundary("bottom", "no_slip")
        engine.set_boundary("left", "no_slip")
        engine.set_boundary("right", "no_slip")
        engine.step(dt=0.01, steps=5)
        resp = engine.step(dt=0.01, steps=5)
        assert resp["time"] == pytest.approx(0.1, abs=1e-10)

    def test_step_default_steps(self, engine):
        engine.create(nx=16, ny=16, lx=1.0, ly=1.0, viscosity=0.01)
        engine.set_boundary("top", "no_slip")
        engine.set_boundary("bottom", "no_slip")
        engine.set_boundary("left", "no_slip")
        engine.set_boundary("right", "no_slip")
        resp = engine.step(dt=0.01)
        assert resp["steps_completed"] == 1
        assert resp["time"] == pytest.approx(0.01, abs=1e-10)

    def test_fields_available_after_step(self, engine):
        engine.create(nx=16, ny=16, lx=1.0, ly=1.0, viscosity=0.01)
        engine.set_boundary("top", "velocity", value=[1.0, 0.0])
        engine.set_boundary("bottom", "no_slip")
        engine.set_boundary("left", "no_slip")
        engine.set_boundary("right", "no_slip")
        engine.step(dt=0.01, steps=10)
        resp = engine.get_field("velocity_x")
        assert resp["shape"] == [16, 16]

    def test_status_shows_time(self, engine):
        engine.create(nx=16, ny=16, lx=1.0, ly=1.0, viscosity=0.01)
        engine.set_boundary("top", "no_slip")
        engine.set_boundary("bottom", "no_slip")
        engine.set_boundary("left", "no_slip")
        engine.set_boundary("right", "no_slip")
        engine.step(dt=0.005, steps=20)
        resp = engine.status()
        assert resp["time"] == pytest.approx(0.1, abs=1e-10)


class TestVorticity:
    """Test vorticity field computation."""

    def test_vorticity_field(self, engine):
        engine.create(nx=16, ny=16, lx=1.0, ly=1.0, viscosity=0.01)
        engine.set_boundary("top", "velocity", value=[1.0, 0.0])
        engine.set_boundary("bottom", "no_slip")
        engine.set_boundary("left", "no_slip")
        engine.set_boundary("right", "no_slip")
        engine.solve_steady(tolerance=1e-4)
        resp = engine.get_field("vorticity")
        assert "shape" in resp
        assert "data" in resp

    def test_vorticity_value(self, engine):
        engine.create(nx=16, ny=16, lx=1.0, ly=1.0, viscosity=0.01)
        engine.set_boundary("top", "velocity", value=[1.0, 0.0])
        engine.set_boundary("bottom", "no_slip")
        engine.set_boundary("left", "no_slip")
        engine.set_boundary("right", "no_slip")
        engine.solve_steady(tolerance=1e-4)
        resp = engine.get_value("vorticity", [0.5, 0.5])
        assert "value" in resp
        assert isinstance(resp["value"], float)

    def test_vorticity_profile(self, engine):
        engine.create(nx=16, ny=16, lx=1.0, ly=1.0, viscosity=0.01)
        engine.set_boundary("top", "velocity", value=[1.0, 0.0])
        engine.set_boundary("bottom", "no_slip")
        engine.set_boundary("left", "no_slip")
        engine.set_boundary("right", "no_slip")
        engine.solve_steady(tolerance=1e-4)
        resp = engine.get_profile("vorticity", "vertical", 0.5, n_points=10)
        assert len(resp["coordinates"]) == 10
        assert len(resp["values"]) == 10


class TestLidDrivenCavity:
    """Test lid-driven cavity flow against Ghia et al. (1982) reference data.

    Ghia, Ghia & Shin, "High-Re Solutions for Incompressible Flow Using the
    Navier-Stokes Equations and a Multigrid Method", J. Comp. Physics 48, 387-411.
    """

    # Selected Ghia data points for Re=100: (y, u) along vertical centerline
    GHIA_RE100_U = [
        (1.0000, 1.00000),
        (0.9766, 0.84123),
        (0.9688, 0.78871),
        (0.9609, 0.73722),
        (0.5000, -0.06080),
        (0.0547, -0.24533),
        (0.0000, 0.00000),
    ]

    def test_cavity_re100_convergence(self, engine):
        """Lid-driven cavity at Re=100 should converge."""
        engine.create(nx=32, ny=32, lx=1.0, ly=1.0, viscosity=0.01)
        engine.set_boundary("top", "velocity", value=[1.0, 0.0])
        engine.set_boundary("bottom", "no_slip")
        engine.set_boundary("left", "no_slip")
        engine.set_boundary("right", "no_slip")
        resp = engine.solve_steady(tolerance=1e-5, max_iterations=50000)
        assert resp["converged"] is True

    def test_cavity_re100_selected_points(self, engine):
        """Check selected Ghia reference points at Re=100, abs error < 0.05."""
        engine.create(nx=32, ny=32, lx=1.0, ly=1.0, viscosity=0.01)
        engine.set_boundary("top", "velocity", value=[1.0, 0.0])
        engine.set_boundary("bottom", "no_slip")
        engine.set_boundary("left", "no_slip")
        engine.set_boundary("right", "no_slip")
        engine.solve_steady(tolerance=1e-6, max_iterations=50000)

        resp = engine.get_profile("velocity_x", "vertical", 0.5, n_points=50)
        coords = resp["coordinates"]
        values = resp["values"]

        for y_ref, u_ref in self.GHIA_RE100_U:
            # Find closest computed point
            idx = min(range(len(coords)), key=lambda i: abs(coords[i] - y_ref))
            u_num = values[idx]
            abs_err = abs(u_num - u_ref)
            assert abs_err < 0.05, \
                f"Ghia Re=100: at y={y_ref:.4f}, u_num={u_num:.5f}, u_ref={u_ref:.5f}, err={abs_err:.4f}"


class TestSteadyNavierStokes:
    """Test that solve_steady works for Navier-Stokes (not just Stokes)."""

    def test_solve_steady_with_advection(self, engine):
        """solve_steady at Re=100 should produce a non-trivial velocity field."""
        engine.create(nx=32, ny=32, lx=1.0, ly=1.0, viscosity=0.01)
        engine.set_boundary("top", "velocity", value=[1.0, 0.0])
        engine.set_boundary("bottom", "no_slip")
        engine.set_boundary("left", "no_slip")
        engine.set_boundary("right", "no_slip")
        resp = engine.solve_steady(tolerance=1e-5, max_iterations=50000)
        assert resp["converged"] is True

        # Check that the velocity field is non-trivial (not all zeros)
        vx = engine.get_field("velocity_x")
        data = vx["data"]
        max_val = max(abs(data[i][j]) for i in range(len(data)) for j in range(len(data[0])))
        assert max_val > 0.1, "Velocity field should be non-trivial"

    def test_stokes_backward_compat(self, engine):
        """Low Re solve_steady should still work (backward compatible with Stage 1)."""
        engine.create(nx=16, ny=16, lx=1.0, ly=1.0, viscosity=1.0)
        engine.set_boundary("top", "velocity", value=[0.001, 0.0])
        engine.set_boundary("bottom", "no_slip")
        engine.set_boundary("left", "no_slip")
        engine.set_boundary("right", "no_slip")
        resp = engine.solve_steady(tolerance=1e-6, max_iterations=50000)
        assert resp["converged"] is True
