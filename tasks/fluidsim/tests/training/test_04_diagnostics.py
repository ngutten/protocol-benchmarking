"""Stage 4 training tests: Flow diagnostics API and basic checks."""
import pytest
import json
import os
import tempfile


class TestDiagnosticsAPI:
    """Test get_diagnostics and get_diagnostic_history commands."""

    def test_get_diagnostics_basic(self, engine):
        """Diagnostics should return kinetic energy and enstrophy for cavity flow."""
        engine.create(nx=16, ny=16, lx=1.0, ly=1.0, viscosity=0.01)
        engine.set_boundary("top", "velocity", value=[1.0, 0.0])
        engine.set_boundary("bottom", "no_slip")
        engine.set_boundary("left", "no_slip")
        engine.set_boundary("right", "no_slip")
        engine.solve_steady(tolerance=1e-4)

        resp = engine.get_diagnostics()
        assert "kinetic_energy" in resp
        assert "enstrophy" in resp
        assert resp["kinetic_energy"] > 0
        assert resp["enstrophy"] > 0

    def test_get_diagnostics_before_solve(self, engine):
        engine.create(nx=16, ny=16, lx=1.0, ly=1.0, viscosity=0.01)
        engine.set_boundary("top", "no_slip")
        engine.set_boundary("bottom", "no_slip")
        engine.set_boundary("left", "no_slip")
        engine.set_boundary("right", "no_slip")
        engine.expect_error({"command": "get_diagnostics"}, "No solution")

    def test_mass_flux_conservation(self, engine):
        """Mass flux through boundaries should be conserved (net flux ~ 0 for closed domain)."""
        engine.create(nx=16, ny=16, lx=1.0, ly=1.0, viscosity=0.01)
        engine.set_boundary("top", "velocity", value=[1.0, 0.0])
        engine.set_boundary("bottom", "no_slip")
        engine.set_boundary("left", "no_slip")
        engine.set_boundary("right", "no_slip")
        engine.solve_steady(tolerance=1e-5)

        resp = engine.get_diagnostics()
        assert "mass_flux" in resp
        flux = resp["mass_flux"]
        # Net mass flux should be approximately zero for a closed cavity
        total = sum(flux.values())
        assert abs(total) < 1e-3, f"Net mass flux should be ~0, got {total}"


class TestDragLift:
    """Test drag and lift diagnostics with obstacles."""

    def test_drag_positive(self, engine):
        """Drag on a cylinder in cross-flow should be positive."""
        engine.create(nx=64, ny=32, lx=2.0, ly=1.0, viscosity=0.05)
        engine.set_boundary("left", "inflow", profile="uniform", velocity=[1.0, 0.0])
        engine.set_boundary("right", "outflow")
        engine.set_boundary("top", "no_slip")
        engine.set_boundary("bottom", "no_slip")
        engine.add_obstacle("circle", center=[0.5, 0.5], radius=0.1)
        engine.solve_steady(tolerance=1e-4, max_iterations=50000)

        resp = engine.get_diagnostics()
        assert "drag" in resp
        assert resp["drag"] > 0, "Drag should be positive for flow past cylinder"

    def test_no_drag_without_obstacle(self, engine):
        """Diagnostics without obstacles should not include drag/lift."""
        engine.create(nx=16, ny=16, lx=1.0, ly=1.0, viscosity=0.01)
        engine.set_boundary("top", "velocity", value=[1.0, 0.0])
        engine.set_boundary("bottom", "no_slip")
        engine.set_boundary("left", "no_slip")
        engine.set_boundary("right", "no_slip")
        engine.solve_steady(tolerance=1e-4)

        resp = engine.get_diagnostics()
        assert "drag" not in resp or resp.get("drag") is None


class TestDiagnosticHistory:
    """Test time history recording of diagnostics."""

    def test_history_after_steps(self, engine):
        """Diagnostic history should have entries for each step."""
        engine.create(nx=16, ny=16, lx=1.0, ly=1.0, viscosity=0.01)
        engine.set_boundary("top", "velocity", value=[1.0, 0.0])
        engine.set_boundary("bottom", "no_slip")
        engine.set_boundary("left", "no_slip")
        engine.set_boundary("right", "no_slip")

        engine.step(dt=0.01, steps=5)

        resp = engine.get_diagnostic_history("kinetic_energy")
        assert "times" in resp
        assert "values" in resp
        assert len(resp["times"]) > 0
        assert len(resp["values"]) == len(resp["times"])

    def test_history_unknown_diagnostic(self, engine):
        engine.create(nx=16, ny=16, lx=1.0, ly=1.0, viscosity=0.01)
        engine.set_boundary("top", "no_slip")
        engine.set_boundary("bottom", "no_slip")
        engine.set_boundary("left", "no_slip")
        engine.set_boundary("right", "no_slip")
        engine.step(dt=0.01, steps=1)
        engine.expect_error(
            {"command": "get_diagnostic_history", "diagnostic": "nonexistent"},
            "Unknown diagnostic"
        )

    def test_history_empty_before_stepping(self, engine):
        """Before any time stepping, history should be empty."""
        engine.create(nx=16, ny=16, lx=1.0, ly=1.0, viscosity=0.01)
        engine.set_boundary("top", "no_slip")
        engine.set_boundary("bottom", "no_slip")
        engine.set_boundary("left", "no_slip")
        engine.set_boundary("right", "no_slip")
        engine.solve_steady(tolerance=1e-4)

        resp = engine.get_diagnostic_history("kinetic_energy")
        assert resp["times"] == []
        assert resp["values"] == []


class TestConfigDrivenDiagnostics:
    """Test diagnostics specified via config files."""

    def test_config_with_diagnostics(self, engine):
        config = {
            "grid": {"nx": 16, "ny": 16, "lx": 1.0, "ly": 1.0},
            "fluid": {"viscosity": 0.01},
            "boundaries": {
                "top": {"type": "velocity", "value": [1.0, 0.0]},
                "bottom": {"type": "no_slip"},
                "left": {"type": "no_slip"},
                "right": {"type": "no_slip"},
            },
            "diagnostics": ["kinetic_energy", "enstrophy"],
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(config, f)
            config_path = f.name
        try:
            engine.load_config(config_path)
            engine.solve_steady(tolerance=1e-4)
            resp = engine.get_diagnostics()
            assert "kinetic_energy" in resp
            assert "enstrophy" in resp
        finally:
            os.unlink(config_path)
