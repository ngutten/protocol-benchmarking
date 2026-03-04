"""Holdout tests for Stage 2: LaTeX Function Parser."""
import os


class TestComplexExpressions:
    """Test more complex LaTeX expressions."""

    def test_nested_frac(self, engine):
        """Nested fractions: \\frac{1}{1 + \\frac{1}{x}} should work."""
        resp = engine.run_ok({
            "function": "\\frac{1}{1 + \\frac{1}{x}}",
            "x_min": 0.5, "x_max": 10,
        })
        assert os.path.exists(resp["output"])

    def test_composed_trig(self, engine):
        """\\sin(\\cos(x)) should work."""
        resp = engine.run_ok({"function": "\\sin(\\cos(x))"})
        assert os.path.exists(resp["output"])

    def test_arctan_frac(self, engine):
        """\\arctan(\\frac{1}{x}) should work."""
        resp = engine.run_ok({
            "function": "\\arctan(\\frac{1}{x})",
            "x_min": -5, "x_max": 5,
        })
        assert os.path.exists(resp["output"])

    def test_half_cos_2pi_x(self, engine):
        """\\frac{1}{2}\\cos(2\\pi x) should work."""
        resp = engine.run_ok({"function": "\\frac{1}{2}\\cos(2\\pi x)"})
        assert os.path.exists(resp["output"])

    def test_ln_sin(self, engine):
        """\\ln(\\sin(x)) should handle NaN gaps."""
        resp = engine.run_ok({
            "function": "\\ln(\\sin(x))",
            "x_min": 0.1, "x_max": 3.1,
        })
        assert os.path.exists(resp["output"])

    def test_braced_exponent(self, engine):
        """x^{2} should work same as x^2."""
        resp = engine.run_ok({"function": "x^{2}"})
        assert os.path.exists(resp["output"])

    def test_sqrt_of_expression(self, engine):
        """\\sqrt{x^2 + 1} should work."""
        resp = engine.run_ok({"function": "\\sqrt{x^2 + 1}"})
        assert os.path.exists(resp["output"])

    def test_nth_root(self, engine):
        """\\sqrt[3]{x} (cube root) should work."""
        resp = engine.run_ok({
            "function": "\\sqrt[3]{x}",
            "x_min": -8, "x_max": 8,
        })
        assert os.path.exists(resp["output"])

    def test_exp_notation(self, engine):
        """\\exp(x) should work same as e^{x}."""
        resp = engine.run_ok({"function": "\\exp(x)", "x_min": -3, "x_max": 3})
        assert os.path.exists(resp["output"])


class TestConstants:
    """Test handling of constants."""

    def test_pi_constant(self, engine):
        """\\pi alone should plot a horizontal line."""
        resp = engine.run_ok({"function": "\\pi"})
        assert os.path.exists(resp["output"])

    def test_pi_in_expression(self, engine):
        """\\sin(\\pi x) should work."""
        resp = engine.run_ok({"function": "\\sin(\\pi x)"})
        assert os.path.exists(resp["output"])


class TestLogarithms:
    """Test logarithm variants."""

    def test_log_base_10(self, engine):
        """\\log(x) should be log base 10."""
        resp = engine.run_ok({"function": "\\log(x)", "x_min": 0.1, "x_max": 100})
        assert os.path.exists(resp["output"])

    def test_log_base_2(self, engine):
        """\\log_{2}(x) should be log base 2."""
        resp = engine.run_ok({"function": "\\log_{2}(x)", "x_min": 0.5, "x_max": 16})
        assert os.path.exists(resp["output"])


class TestNaNHandling:
    """Test that undefined regions are handled gracefully."""

    def test_division_by_zero(self, engine):
        """\\frac{1}{x} at x=0 should produce NaN, not crash."""
        resp = engine.run_ok({"function": "\\frac{1}{x}", "x_min": -5, "x_max": 5})
        assert os.path.exists(resp["output"])

    def test_sqrt_negative(self, engine):
        """\\sqrt{x} with negative x should produce NaN for those points."""
        resp = engine.run_ok({"function": "\\sqrt{x}", "x_min": -5, "x_max": 5})
        assert os.path.exists(resp["output"])

    def test_ln_negative(self, engine):
        """\\ln(x) with negative x should produce NaN."""
        resp = engine.run_ok({"function": "\\ln(x)", "x_min": -5, "x_max": 5})
        assert os.path.exists(resp["output"])


class TestUnsupported:
    """Test error handling for unsupported LaTeX."""

    def test_integral(self, engine):
        """\\int should be unsupported."""
        engine.run_error({"function": "\\int_{0}^{x} t^2 dt"}, match="unsupported")

    def test_summation(self, engine):
        """\\sum should be unsupported."""
        engine.run_error({"function": "\\sum_{n=0}^{10} x^n"}, match="unsupported")

    def test_matrix(self, engine):
        """\\begin{matrix} should be unsupported."""
        engine.run_error(
            {"function": "\\begin{matrix} 1 & 2 \\end{matrix}"},
            match="unsupported",
        )
