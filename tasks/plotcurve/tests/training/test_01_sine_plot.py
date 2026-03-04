"""Training tests for Stage 1: Sine Wave Plot."""
import os
import json
import math


class TestBasicPlot:
    """Test that the default sine wave plot is generated correctly."""

    def test_default_request(self, engine):
        """Empty request should produce a plot with defaults."""
        resp = engine.run_ok({})
        assert os.path.exists(resp["output"])
        assert resp["output"].endswith(".png")

    def test_custom_output_path(self, engine, tmp_path):
        """Specifying output path should write there."""
        out = str(tmp_path / "custom.png")
        resp = engine.run_ok({"output": out})
        assert resp["output"] == out
        assert os.path.exists(out)

    def test_custom_range(self, engine):
        """Custom x_min/x_max should work."""
        resp = engine.run_ok({"x_min": 0, "x_max": 5})
        assert os.path.exists(resp["output"])

    def test_custom_n_points(self, engine):
        """Custom n_points should work."""
        resp = engine.run_ok({"n_points": 100})
        assert os.path.exists(resp["output"])

    def test_title(self, engine):
        """Providing a title should not cause errors."""
        resp = engine.run_ok({"title": "My Sine Wave"})
        assert os.path.exists(resp["output"])

    def test_file_is_valid_png(self, engine):
        """Output file should be a valid PNG (check magic bytes)."""
        resp = engine.run_ok({})
        with open(resp["output"], "rb") as f:
            header = f.read(8)
        # PNG magic bytes
        assert header[:4] == b'\x89PNG'


class TestValidation:
    """Test input validation and error handling."""

    def test_x_min_ge_x_max(self, engine):
        """x_min >= x_max should return an error."""
        engine.run_error({"x_min": 5, "x_max": 5}, match="x_min")

    def test_x_min_gt_x_max(self, engine):
        """x_min > x_max should return an error."""
        engine.run_error({"x_min": 10, "x_max": 0}, match="x_min")

    def test_n_points_too_small(self, engine):
        """n_points < 2 should return an error."""
        engine.run_error({"n_points": 1}, match="n_points")

    def test_n_points_zero(self, engine):
        """n_points = 0 should return an error."""
        engine.run_error({"n_points": 0}, match="n_points")


class TestOutputFormat:
    """Test JSON response structure."""

    def test_success_has_ok_and_output(self, engine):
        """Success response must have 'ok' and 'output' keys."""
        resp = engine.run({})
        assert "ok" in resp
        assert "output" in resp
        assert resp["ok"] is True

    def test_error_has_error_key(self, engine):
        """Error response must have 'error' key."""
        resp = engine.run({"x_min": 10, "x_max": 0})
        assert "error" in resp
