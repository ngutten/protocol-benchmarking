"""Performance benchmarks for Stage 6: Type coercion rules.

Holdout — never provided to the LLM.
"""
import time


class TestCoercionPerf:
    def _populate_mixed(self, engine, n=200):
        """Insert rows with mixed types to stress coercion paths."""
        engine.execute("CREATE TABLE perf (id, val)")
        for i in range(n):
            if i % 5 == 0:
                engine.execute(f"INSERT INTO perf VALUES ({i}, {i})")
            elif i % 5 == 1:
                engine.execute(f"INSERT INTO perf VALUES ({i}, {i}.5)")
            elif i % 5 == 2:
                engine.execute(f"INSERT INTO perf VALUES ({i}, '{i}')")
            elif i % 5 == 3:
                engine.execute(f"INSERT INTO perf VALUES ({i}, true)")
            else:
                engine.execute(f"INSERT INTO perf VALUES ({i}, null)")

    def test_cross_type_comparison_200_rows(self, engine):
        """WHERE with cross-type comparisons forcing coercion."""
        self._populate_mixed(engine, 200)
        start = time.perf_counter()
        for _ in range(20):
            engine.query_rows("SELECT id FROM perf WHERE val > 50")
        elapsed = time.perf_counter() - start
        print(f'{{"bench_metric": "ops_per_second", "test": "test_cross_type_comparison_200_rows", "value": {20 / elapsed:.2f}, "iterations": 20, "duration_seconds": {elapsed:.6f}}}')

    def test_mixed_type_arithmetic(self, engine):
        """Arithmetic on mixed-type column."""
        self._populate_mixed(engine, 200)
        start = time.perf_counter()
        for _ in range(20):
            engine.query_rows("SELECT val + 1 FROM perf")
        elapsed = time.perf_counter() - start
        print(f'{{"bench_metric": "ops_per_second", "test": "test_mixed_type_arithmetic", "value": {20 / elapsed:.2f}, "iterations": 20, "duration_seconds": {elapsed:.6f}}}')

    def test_typeof_scan(self, engine):
        """TYPEOF() over 200 mixed-type rows."""
        self._populate_mixed(engine, 200)
        start = time.perf_counter()
        for _ in range(20):
            engine.query_rows("SELECT TYPEOF(val) FROM perf")
        elapsed = time.perf_counter() - start
        print(f'{{"bench_metric": "ops_per_second", "test": "test_typeof_scan", "value": {20 / elapsed:.2f}, "iterations": 20, "duration_seconds": {elapsed:.6f}}}')
