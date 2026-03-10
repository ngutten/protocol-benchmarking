"""Stage 3 training tests: Complex boundary conditions and obstacles."""
import pytest
import json
import os
import tempfile


class TestInflowOutflow:
    """Test inflow and outflow boundary conditions."""

    def test_inflow_uniform(self, engine):
        engine.create(nx=32, ny=16, lx=2.0, ly=1.0, viscosity=0.01)
        resp = engine.set_boundary("left", "inflow", profile="uniform", velocity=[1.0, 0.0])
        assert resp["status"] == "ok"

    def test_inflow_parabolic(self, engine):
        engine.create(nx=32, ny=16, lx=2.0, ly=1.0, viscosity=0.01)
        resp = engine.set_boundary("left", "inflow", profile="parabolic", velocity_max=1.5)
        assert resp["status"] == "ok"

    def test_outflow(self, engine):
        engine.create(nx=32, ny=16, lx=2.0, ly=1.0, viscosity=0.01)
        resp = engine.set_boundary("right", "outflow")
        assert resp["status"] == "ok"

    def test_inflow_outflow_channel(self, engine):
        """Channel flow with inflow/outflow should produce non-trivial solution."""
        engine.create(nx=32, ny=16, lx=2.0, ly=1.0, viscosity=0.05)
        engine.set_boundary("left", "inflow", profile="uniform", velocity=[1.0, 0.0])
        engine.set_boundary("right", "outflow")
        engine.set_boundary("top", "no_slip")
        engine.set_boundary("bottom", "no_slip")
        resp = engine.solve_steady(tolerance=1e-4, max_iterations=50000)
        assert resp["converged"] is True

        # Velocity at center should be positive (flow in x-direction)
        val = engine.get_value("velocity_x", [1.0, 0.5])
        assert val["value"] > 0.1, "Flow should be moving in x-direction"


class TestPeriodicBC:
    """Test periodic boundary conditions."""

    def test_periodic_left_right(self, engine):
        engine.create(nx=16, ny=16, lx=1.0, ly=1.0, viscosity=0.01)
        resp1 = engine.set_boundary("left", "periodic", paired_with="right")
        assert resp1["status"] == "ok"
        resp2 = engine.set_boundary("right", "periodic", paired_with="left")
        assert resp2["status"] == "ok"

    def test_periodic_top_bottom(self, engine):
        engine.create(nx=16, ny=16, lx=1.0, ly=1.0, viscosity=0.01)
        resp1 = engine.set_boundary("top", "periodic", paired_with="bottom")
        assert resp1["status"] == "ok"
        resp2 = engine.set_boundary("bottom", "periodic", paired_with="top")
        assert resp2["status"] == "ok"

    def test_periodic_unpaired_error(self, engine):
        """Setting only one side as periodic without pairing should error."""
        engine.create(nx=16, ny=16, lx=1.0, ly=1.0, viscosity=0.01)
        engine.set_boundary("left", "periodic", paired_with="right")
        engine.set_boundary("top", "no_slip")
        engine.set_boundary("bottom", "no_slip")
        # Right is not periodic — solve should fail or set_boundary should warn
        # At minimum, setting incompatible pairing should error
        engine.expect_error(
            {"command": "set_boundary", "boundary": "right", "type": "velocity", "value": [1.0, 0.0]},
        )


class TestObstacles:
    """Test immersed boundary obstacles."""

    def test_add_circle_obstacle(self, engine):
        engine.create(nx=32, ny=32, lx=2.0, ly=1.0, viscosity=0.01)
        resp = engine.add_obstacle("circle", center=[0.5, 0.5], radius=0.1)
        assert "obstacle_id" in resp
        assert isinstance(resp["obstacle_id"], int)

    def test_add_rectangle_obstacle(self, engine):
        engine.create(nx=32, ny=32, lx=2.0, ly=1.0, viscosity=0.01)
        resp = engine.add_obstacle("rectangle", lower_left=[0.3, 0.3], upper_right=[0.5, 0.5])
        assert "obstacle_id" in resp

    def test_multiple_obstacles(self, engine):
        engine.create(nx=32, ny=32, lx=2.0, ly=1.0, viscosity=0.01)
        r1 = engine.add_obstacle("circle", center=[0.3, 0.5], radius=0.05)
        r2 = engine.add_obstacle("circle", center=[0.7, 0.5], radius=0.05)
        assert r1["obstacle_id"] != r2["obstacle_id"]

    def test_obstacle_before_create(self, engine):
        engine.expect_error(
            {"command": "add_obstacle", "type": "circle", "center": [0.5, 0.5], "radius": 0.1},
            "No simulation"
        )

    def test_invalid_obstacle_type(self, engine):
        engine.create(nx=32, ny=32, lx=2.0, ly=1.0, viscosity=0.01)
        engine.expect_error(
            {"command": "add_obstacle", "type": "triangle", "points": [[0, 0], [1, 0], [0.5, 1]]},
            "Invalid obstacle type"
        )

    def test_flow_around_cylinder(self, engine):
        """Flow around a cylinder should produce non-trivial solution."""
        engine.create(nx=64, ny=32, lx=2.0, ly=1.0, viscosity=0.05)
        engine.set_boundary("left", "inflow", profile="uniform", velocity=[1.0, 0.0])
        engine.set_boundary("right", "outflow")
        engine.set_boundary("top", "no_slip")
        engine.set_boundary("bottom", "no_slip")
        engine.add_obstacle("circle", center=[0.5, 0.5], radius=0.1)
        resp = engine.solve_steady(tolerance=1e-4, max_iterations=50000)
        assert resp["converged"] is True

        # Check that velocity behind cylinder is reduced (wake)
        upstream = engine.get_value("velocity_x", [0.2, 0.5])
        downstream = engine.get_value("velocity_x", [0.7, 0.5])
        assert upstream["value"] > downstream["value"], \
            "Velocity in wake should be less than upstream"


class TestLoadConfig:
    """Test loading configuration from JSON files."""

    def test_load_config_basic(self, engine):
        config = {
            "grid": {"nx": 16, "ny": 16, "lx": 1.0, "ly": 1.0},
            "fluid": {"viscosity": 0.1},
            "boundaries": {
                "top": {"type": "velocity", "value": [1.0, 0.0]},
                "bottom": {"type": "no_slip"},
                "left": {"type": "no_slip"},
                "right": {"type": "no_slip"},
            },
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(config, f)
            config_path = f.name
        try:
            resp = engine.load_config(config_path)
            assert resp["status"] == "ok"
            # Verify the config was applied
            status = engine.status()
            assert status["grid"]["nx"] == 16
        finally:
            os.unlink(config_path)

    def test_load_config_with_obstacles(self, engine):
        config = {
            "grid": {"nx": 32, "ny": 32, "lx": 2.0, "ly": 1.0},
            "fluid": {"viscosity": 0.01},
            "boundaries": {
                "top": {"type": "no_slip"},
                "bottom": {"type": "no_slip"},
                "left": {"type": "inflow", "profile": "uniform", "velocity": [1.0, 0.0]},
                "right": {"type": "outflow"},
            },
            "obstacles": [
                {"type": "circle", "center": [0.5, 0.5], "radius": 0.1},
            ],
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(config, f)
            config_path = f.name
        try:
            resp = engine.load_config(config_path)
            assert resp["status"] == "ok"
        finally:
            os.unlink(config_path)

    def test_load_config_file_not_found(self, engine):
        engine.expect_error(
            {"command": "load_config", "path": "/nonexistent/path.json"},
            "not found"
        )
