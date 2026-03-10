"""Performance benchmarks for Stage 2: LaTeX function parser.

Holdout — never provided to the LLM.
Measures parsing + evaluation + rendering latency across varying
LaTeX complexity levels.
"""
import time


class TestLatexParserPerf:
    def test_simple_function(self, engine):
        """Latency for a simple LaTeX expression: \\sin(x)."""
        start = time.perf_counter()
        for _ in range(10):
            engine.run_ok({"function": r"\sin(x)"})
        elapsed = time.perf_counter() - start
        print(f'{{"bench_metric": "ops_per_second", "test": "test_simple_function", "value": {10 / elapsed:.2f}, "iterations": 10, "duration_seconds": {elapsed:.6f}}}')

    def test_polynomial(self, engine):
        """Latency for a polynomial: x^3 - 2x^2 + x - 1."""
        start = time.perf_counter()
        for _ in range(10):
            engine.run_ok({"function": r"x^3 - 2x^2 + x - 1"})
        elapsed = time.perf_counter() - start
        print(f'{{"bench_metric": "ops_per_second", "test": "test_polynomial", "value": {10 / elapsed:.2f}, "iterations": 10, "duration_seconds": {elapsed:.6f}}}')

    def test_nested_expression(self, engine):
        r"""Latency for nested expression: \frac{\sin(x^2)}{1 + x^2}."""
        start = time.perf_counter()
        for _ in range(10):
            engine.run_ok({"function": r"\frac{\sin(x^2)}{1 + x^2}"})
        elapsed = time.perf_counter() - start
        print(f'{{"bench_metric": "ops_per_second", "test": "test_nested_expression", "value": {10 / elapsed:.2f}, "iterations": 10, "duration_seconds": {elapsed:.6f}}}')

    def test_composite_trig(self, engine):
        r"""Latency for composite trig: \sin(\cos(\arctan(x)))."""
        start = time.perf_counter()
        for _ in range(10):
            engine.run_ok({"function": r"\sin(\cos(\arctan(x)))"})
        elapsed = time.perf_counter() - start
        print(f'{{"bench_metric": "ops_per_second", "test": "test_composite_trig", "value": {10 / elapsed:.2f}, "iterations": 10, "duration_seconds": {elapsed:.6f}}}')

    def test_exponential_gaussian(self, engine):
        r"""Latency for Gaussian: e^{-x^2}."""
        start = time.perf_counter()
        for _ in range(10):
            engine.run_ok({"function": r"e^{-x^2}"})
        elapsed = time.perf_counter() - start
        print(f'{{"bench_metric": "ops_per_second", "test": "test_exponential_gaussian", "value": {10 / elapsed:.2f}, "iterations": 10, "duration_seconds": {elapsed:.6f}}}')

    def test_complex_expression_high_res(self, engine):
        r"""Latency for complex expression at high resolution."""
        start = time.perf_counter()
        for _ in range(6):
            engine.run_ok({
                "function": r"\frac{1}{2}\cos(2\pi x) + \sqrt{x^2 + 1}",
                "n_points": 2000,
            })
        elapsed = time.perf_counter() - start
        print(f'{{"bench_metric": "ops_per_second", "test": "test_complex_expression_high_res", "value": {6 / elapsed:.2f}, "iterations": 6, "duration_seconds": {elapsed:.6f}}}')
