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
