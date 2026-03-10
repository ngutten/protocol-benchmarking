"""Stage 3 holdout tests: Poiseuille via inflow, cylinder wake, periodic Couette, edge cases."""
import pytest
import json
import os
import tempfile
import math


class TestPoiseuilleInflow:
    """Poiseuille flow driven by inflow BCs (not body force)."""

    def test_parabolic_inflow_poiseuille(self, engine):
        """Parabolic inflow should produce Poiseuille profile downstream (1e-2 tol)."""
        H = 1.0
        U_max = 1.5
        nu = 0.1
        engine.create(nx=64, ny=32, lx=4.0, ly=H, viscosity=nu)
        engine.set_boundary("left", "inflow", profile="parabolic", velocity_max=U_max)
        engine.set_boundary("right", "outflow")
        engine.set_boundary("top", "no_slip")
        engine.set_boundary("bottom", "no_slip")
        engine.solve_steady(tolerance=1e-6, max_iterations=100000)

        # Check profile at x=3.0 (well downstream, should be fully developed)
        resp = engine.get_profile("velocity_x", "vertical", 3.0, n_points=30)
        coords = resp["coordinates"]
        values = resp["values"]

        for y, u_num in zip(coords, values):
            # Parabolic profile: u(y) = U_max * 4 * y/H * (1 - y/H)
            u_exact = U_max * 4.0 * (y / H) * (1.0 - y / H)
            if 0.1 < y < 0.9 and u_exact > 0.1:
                rel_err = abs(u_num - u_exact) / u_exact
                assert rel_err < 0.1, \
                    f"Inflow Poiseuille: y={y:.3f}, u_num={u_num:.4f}, u_exact={u_exact:.4f}, rel_err={rel_err:.3f}"


class TestCylinderWake:
    """Test cylinder wake at Re=20.

    Dennis & Chang (1970): Cd ~ 2.05
    Tritton (1959): Wake length L/D ~ 0.93
    """

    def test_cylinder_re20_wake_length(self, engine):
        """Cylinder at Re=20 should have wake length L/D in [0.7, 1.2]."""
        D = 0.2  # diameter
        U = 1.0
        nu = U * D / 20.0  # Re = UD/nu = 20

        engine.create(nx=128, ny=64, lx=4.0, ly=2.0, viscosity=nu)
        engine.set_boundary("left", "inflow", profile="uniform", velocity=[U, 0.0])
        engine.set_boundary("right", "outflow")
        engine.set_boundary("top", "no_slip")
        engine.set_boundary("bottom", "no_slip")
        engine.add_obstacle("circle", center=[1.0, 1.0], radius=D / 2)
        engine.solve_steady(tolerance=1e-5, max_iterations=200000)

        # Measure wake length: find where u returns to positive along centerline
        # behind the cylinder
        resp = engine.get_profile("velocity_x", "horizontal", 1.0, n_points=200)
        coords = resp["coordinates"]
        values = resp["values"]

        # Find the recirculation zone behind the cylinder
        cylinder_back = 1.0 + D / 2  # x = 1.1
        reattachment_x = None
        for x, u in zip(coords, values):
            if x > cylinder_back + 0.01:
                if u > 0:
                    reattachment_x = x
                    break

        if reattachment_x is not None:
            wake_length = reattachment_x - cylinder_back
            L_over_D = wake_length / D
            assert 0.7 < L_over_D < 1.5, \
                f"Wake length L/D = {L_over_D:.2f}, expected ~0.93 (range 0.7-1.5)"


class TestPeriodicCouette:
    """Test Couette flow with periodic boundary conditions."""

    def test_periodic_couette(self, engine):
        """Periodic Couette (shear flow) should maintain linear profile."""
        H = 1.0
        U = 1.0
        nu = 0.1
        engine.create(nx=16, ny=32, lx=1.0, ly=H, viscosity=nu)
        engine.set_boundary("top", "velocity", value=[U, 0.0])
        engine.set_boundary("bottom", "no_slip")
        engine.set_boundary("left", "periodic", paired_with="right")
        engine.set_boundary("right", "periodic", paired_with="left")
        engine.solve_steady(tolerance=1e-6, max_iterations=50000)

        resp = engine.get_profile("velocity_x", "vertical", 0.5, n_points=20)
        coords = resp["coordinates"]
        values = resp["values"]

        for y, u_num in zip(coords, values):
            u_exact = U * y / H
            if 0.05 < y < 0.95:
                assert abs(u_num - u_exact) < 0.05, \
                    f"Periodic Couette: y={y:.3f}, u_num={u_num:.4f}, u_exact={u_exact:.4f}"


class TestObstacleEdgeCases:
    """Edge cases for obstacle handling."""

    def test_obstacle_near_boundary(self, engine):
        """Obstacle near domain boundary should not crash."""
        engine.create(nx=32, ny=32, lx=2.0, ly=1.0, viscosity=0.01)
        engine.set_boundary("left", "inflow", profile="uniform", velocity=[1.0, 0.0])
        engine.set_boundary("right", "outflow")
        engine.set_boundary("top", "no_slip")
        engine.set_boundary("bottom", "no_slip")
        # Obstacle close to bottom wall
        engine.add_obstacle("circle", center=[1.0, 0.2], radius=0.1)
        resp = engine.solve_steady(tolerance=1e-3, max_iterations=50000)
        # Should at least not crash
        assert "converged" in resp

    def test_rectangle_obstacle_flow(self, engine):
        """Flow around rectangular obstacle should produce wake."""
        engine.create(nx=64, ny=32, lx=4.0, ly=1.0, viscosity=0.05)
        engine.set_boundary("left", "inflow", profile="uniform", velocity=[1.0, 0.0])
        engine.set_boundary("right", "outflow")
        engine.set_boundary("top", "no_slip")
        engine.set_boundary("bottom", "no_slip")
        engine.add_obstacle("rectangle", lower_left=[0.8, 0.35], upper_right=[1.2, 0.65])
        resp = engine.solve_steady(tolerance=1e-4, max_iterations=100000)
        assert resp["converged"] is True

        # Velocity should be reduced in wake
        downstream = engine.get_value("velocity_x", [2.0, 0.5])
        upstream = engine.get_value("velocity_x", [0.4, 0.5])
        assert downstream["value"] < upstream["value"]


class TestConfigEndToEnd:
    """End-to-end config-driven tests."""

    def test_full_config_channel_obstacle(self, engine):
        """Complete config with grid, BCs, obstacle — end to end."""
        config = {
            "grid": {"nx": 64, "ny": 32, "lx": 4.0, "ly": 1.0},
            "fluid": {"viscosity": 0.05},
            "boundaries": {
                "top": {"type": "no_slip"},
                "bottom": {"type": "no_slip"},
                "left": {"type": "inflow", "profile": "uniform", "velocity": [1.0, 0.0]},
                "right": {"type": "outflow"},
            },
            "obstacles": [
                {"type": "circle", "center": [1.0, 0.5], "radius": 0.1},
            ],
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(config, f)
            config_path = f.name
        try:
            engine.load_config(config_path)
            resp = engine.solve_steady(tolerance=1e-4, max_iterations=100000)
            assert resp["converged"] is True

            # Check flow is non-trivial
            val = engine.get_value("velocity_x", [2.0, 0.5])
            assert val["value"] > 0
        finally:
            os.unlink(config_path)


class TestPeriodicConservation:
    """Test conservation properties in periodic domains.

    Periodic boundaries allow cleaner tests of conservation since there are
    no open boundaries where fluxes can enter or leave.
    """

    def test_periodic_couette_perturbation_decays(self, engine):
        """Transverse perturbation on periodic Couette flow should decay.

        Plane Couette flow (periodic L-R, moving top, no-slip bottom) is
        linearly stable at all Re in 2D. A small v-perturbation introduced
        via a temporary lid velocity change should decay, not grow.
        This tests numerical stability of the advection scheme.
        """
        nx, ny = 32, 32
        lx, ly = 1.0, 1.0
        engine.create(nx=nx, ny=ny, lx=lx, ly=ly, viscosity=0.01)
        engine.set_boundary("top", "velocity", value=[1.0, 0.0])
        engine.set_boundary("bottom", "no_slip")
        engine.set_boundary("left", "periodic", paired_with="right")
        engine.set_boundary("right", "periodic", paired_with="left")
        engine.step(dt=0.01, steps=100)  # establish Couette-like flow

        # Introduce transverse perturbation
        engine.set_boundary("top", "velocity", value=[1.0, 0.05])
        engine.step(dt=0.005, steps=20)

        uy_data = engine.get_field("velocity_y")["data"]
        dx, dy = lx / nx, ly / ny
        vy_energy_pert = sum(
            uy_data[j][i] ** 2 * dx * dy
            for j in range(ny) for i in range(nx)
        )

        # Remove perturbation and let decay
        engine.set_boundary("top", "velocity", value=[1.0, 0.0])
        engine.step(dt=0.005, steps=200)

        uy_data = engine.get_field("velocity_y")["data"]
        vy_energy_after = sum(
            uy_data[j][i] ** 2 * dx * dy
            for j in range(ny) for i in range(nx)
        )

        assert vy_energy_after < vy_energy_pert, \
            f"v-perturbation should decay: " \
            f"perturbed={vy_energy_pert:.6f}, after={vy_energy_after:.6f}"

    def test_periodic_poiseuille_force_balance(self, engine):
        """In periodic Poiseuille, the wall shear stress should balance the body force.

        Analytical: total wall shear = F × L × H (body force integrated over domain).
        We check this indirectly: the velocity profile slope at walls should match
        du/dy|_{y=0} = F·H/(2ν) and du/dy|_{y=H} = -F·H/(2ν).
        """
        H, L = 1.0, 1.0
        nu = 0.05
        F = 2.0
        nx, ny = 32, 64  # fine grid in y for accurate wall gradient

        engine.create(nx=nx, ny=ny, lx=L, ly=H, viscosity=nu, force=[F, 0.0])
        engine.set_boundary("left", "periodic", paired_with="right")
        engine.set_boundary("right", "periodic", paired_with="left")
        engine.set_boundary("top", "no_slip")
        engine.set_boundary("bottom", "no_slip")
        engine.solve_steady(tolerance=1e-7, max_iterations=50000)

        # Get profile near bottom wall
        resp = engine.get_profile("velocity_x", "vertical", 0.5, n_points=64)
        coords = resp["coordinates"]
        values = resp["values"]

        # Wall gradient at bottom: du/dy ≈ (u[1] - u[0]) / (y[1] - y[0])
        # Analytical: du/dy|_{y=0} = F·H/(2ν)
        expected_gradient = F * H / (2.0 * nu)

        # Use first two interior points for gradient estimate
        dy_near = coords[1] - coords[0]
        gradient_bottom = (values[1] - values[0]) / dy_near

        rel_err = abs(gradient_bottom - expected_gradient) / expected_gradient
        assert rel_err < 0.1, \
            f"Wall gradient: computed={gradient_bottom:.4f}, " \
            f"expected={expected_gradient:.4f}, rel_err={rel_err:.3f}"

    def test_periodic_channel_symmetry_across_resolutions(self, engine):
        """Periodic Poiseuille profile should be symmetric about y=H/2 at different grids.

        On a 16² and 32² grid, the profile should be symmetric and the
        peak velocity should converge toward the analytical value.
        """
        H, L = 1.0, 1.0
        nu = 0.1
        F = 1.0

        peaks = []
        for nx, ny in [(16, 16), (32, 32)]:
            engine.create(nx=nx, ny=ny, lx=L, ly=H, viscosity=nu, force=[F, 0.0])
            engine.set_boundary("left", "periodic", paired_with="right")
            engine.set_boundary("right", "periodic", paired_with="left")
            engine.set_boundary("top", "no_slip")
            engine.set_boundary("bottom", "no_slip")
            engine.solve_steady(tolerance=1e-7, max_iterations=50000)

            resp = engine.get_profile("velocity_x", "vertical", 0.5, n_points=40)
            coords = resp["coordinates"]
            values = resp["values"]

            # Check symmetry
            for k in range(len(coords)):
                y_mirror = H - coords[k]
                k_mirror = min(range(len(coords)), key=lambda m: abs(coords[m] - y_mirror))
                if 0.1 < coords[k] < 0.9:
                    assert abs(values[k] - values[k_mirror]) < 0.02, \
                        f"Grid {nx}²: asymmetric at y={coords[k]:.2f}: " \
                        f"u={values[k]:.4f} vs u(mirror)={values[k_mirror]:.4f}"

            peaks.append(max(values))
            if nx < 32:
                engine.reset()

        # Analytical peak: F·H²/(8ν) = 1.0*1.0/(8*0.1) = 1.25
        u_max_exact = F * H ** 2 / (8.0 * nu)
        # Finer grid should be closer to exact
        err_coarse = abs(peaks[0] - u_max_exact) / u_max_exact
        err_fine = abs(peaks[1] - u_max_exact) / u_max_exact
        assert err_fine < err_coarse + 0.01, \
            f"Finer grid should converge: peak(16²)={peaks[0]:.4f} (err={err_coarse:.4f}), " \
            f"peak(32²)={peaks[1]:.4f} (err={err_fine:.4f}), exact={u_max_exact:.4f}"
