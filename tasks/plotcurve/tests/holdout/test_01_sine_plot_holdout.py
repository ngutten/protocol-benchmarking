"""Holdout tests for Stage 1: Sine Wave Plot."""
import os
import json
import struct


class TestEdgeCases:
    """Edge cases for the basic sine plot."""

    def test_very_large_range(self, engine):
        """Very large x range should still work."""
        resp = engine.run_ok({"x_min": -1000, "x_max": 1000})
        assert os.path.exists(resp["output"])

    def test_very_small_range(self, engine):
        """Very small x range should still produce a plot."""
        resp = engine.run_ok({"x_min": 0, "x_max": 0.001})
        assert os.path.exists(resp["output"])

    def test_negative_range(self, engine):
        """Both bounds negative should work."""
        resp = engine.run_ok({"x_min": -20, "x_max": -5})
        assert os.path.exists(resp["output"])

    def test_large_n_points(self, engine):
        """Large n_points should work (performance test)."""
        resp = engine.run_ok({"n_points": 10000})
        assert os.path.exists(resp["output"])

    def test_n_points_exactly_2(self, engine):
        """Minimum valid n_points should work."""
        resp = engine.run_ok({"n_points": 2})
        assert os.path.exists(resp["output"])

    def test_float_bounds(self, engine):
        """Float bounds should work."""
        resp = engine.run_ok({"x_min": -3.14159, "x_max": 3.14159})
        assert os.path.exists(resp["output"])

    def test_output_overwrites_existing(self, engine, tmp_path):
        """Writing to an existing file should overwrite it."""
        out = str(tmp_path / "existing.png")
        with open(out, "w") as f:
            f.write("old content")
        resp = engine.run_ok({"output": out})
        with open(out, "rb") as f:
            assert f.read(4) == b'\x89PNG'

    def test_empty_title(self, engine):
        """Empty string title should not cause errors."""
        resp = engine.run_ok({"title": ""})
        assert os.path.exists(resp["output"])

    def test_special_chars_in_title(self, engine):
        """Special characters in title should be handled."""
        resp = engine.run_ok({"title": "f(x) = sin(2π·x/5) & more"})
        assert os.path.exists(resp["output"])


class TestInvalidInput:
    """Additional validation edge cases."""

    def test_n_points_negative(self, engine):
        """Negative n_points should error."""
        engine.run_error({"n_points": -5}, match="n_points")

    def test_x_min_equals_x_max_float(self, engine):
        """Equal float bounds should error."""
        engine.run_error({"x_min": 3.14, "x_max": 3.14}, match="x_min")
