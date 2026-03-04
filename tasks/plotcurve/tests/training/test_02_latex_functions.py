"""Training tests for Stage 2: LaTeX Function Parser."""
import os
import math


class TestBasicFunctions:
    """Test parsing and plotting of basic LaTeX functions."""

    def test_sin(self, engine):
        """\\sin(x) should work."""
        resp = engine.run_ok({"function": "\\sin(x)"})
        assert os.path.exists(resp["output"])

    def test_cos(self, engine):
        """\\cos(x) should work."""
        resp = engine.run_ok({"function": "\\cos(x)"})
        assert os.path.exists(resp["output"])

    def test_tan(self, engine):
        """\\tan(x) should work."""
        resp = engine.run_ok({"function": "\\tan(x)", "x_min": -1.5, "x_max": 1.5})
        assert os.path.exists(resp["output"])

    def test_polynomial(self, engine):
        """x^2 - 3x + 1 should work."""
        resp = engine.run_ok({"function": "x^2 - 3x + 1"})
        assert os.path.exists(resp["output"])

    def test_exponential(self, engine):
        """e^{-x^2} should work (Gaussian)."""
        resp = engine.run_ok({"function": "e^{-x^2}", "x_min": -3, "x_max": 3})
        assert os.path.exists(resp["output"])

    def test_sqrt(self, engine):
        """\\sqrt{x} should work."""
        resp = engine.run_ok({"function": "\\sqrt{x}", "x_min": 0, "x_max": 10})
        assert os.path.exists(resp["output"])

    def test_ln(self, engine):
        """\\ln(x) should work."""
        resp = engine.run_ok({"function": "\\ln(x)", "x_min": 0.1, "x_max": 10})
        assert os.path.exists(resp["output"])

    def test_frac(self, engine):
        """\\frac{x^2}{1 + x^2} should work."""
        resp = engine.run_ok({"function": "\\frac{x^2}{1 + x^2}"})
        assert os.path.exists(resp["output"])


class TestImplicitMultiplication:
    """Test implicit multiplication handling."""

    def test_coefficient(self, engine):
        """2x should be parsed as 2*x."""
        resp = engine.run_ok({"function": "2x"})
        assert os.path.exists(resp["output"])

    def test_coefficient_with_function(self, engine):
        """3\\sin(x) should be parsed as 3*sin(x)."""
        resp = engine.run_ok({"function": "3\\sin(x)"})
        assert os.path.exists(resp["output"])

    def test_cdot(self, engine):
        """2 \\cdot x should be parsed as 2*x."""
        resp = engine.run_ok({"function": "2 \\cdot x"})
        assert os.path.exists(resp["output"])


class TestFallback:
    """Test backward compatibility with Stage 1."""

    def test_no_function_field(self, engine):
        """Missing function field should use default sine wave."""
        resp = engine.run_ok({})
        assert os.path.exists(resp["output"])

    def test_empty_function(self, engine):
        """Empty function string should use default sine wave."""
        resp = engine.run_ok({"function": ""})
        assert os.path.exists(resp["output"])


class TestErrorHandling:
    """Test error handling for invalid LaTeX."""

    def test_unbalanced_braces(self, engine):
        """Unbalanced braces should return parse error."""
        engine.run_error({"function": "\\frac{x{1+x}"}, match="parse error")

    def test_previous_validation_still_works(self, engine):
        """Stage 1 validation should still work."""
        engine.run_error({"function": "\\sin(x)", "x_min": 5, "x_max": 0}, match="x_min")
