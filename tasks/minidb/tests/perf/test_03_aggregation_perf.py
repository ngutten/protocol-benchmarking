"""Performance benchmarks for Stage 3: Aggregation.

Holdout — never provided to the LLM.
"""
import time


class TestAggregationPerf:
    def _populate(self, engine, n=300):
        engine.execute("CREATE TABLE perf (id, category, value)")
        for i in range(n):
            cat = f"cat_{i % 10}"
            engine.execute(f"INSERT INTO perf VALUES ({i}, '{cat}', {i * 1.1})")

    def test_count_300_rows(self, engine):
        self._populate(engine, 300)
        start = time.perf_counter()
        for _ in range(20):
            engine.query_scalar("SELECT COUNT(*) FROM perf")
        elapsed = time.perf_counter() - start
        print(f'{{"bench_metric": "ops_per_second", "test": "test_count_300_rows", "value": {20 / elapsed:.2f}, "iterations": 20, "duration_seconds": {elapsed:.6f}}}')

    def test_sum_avg_300_rows(self, engine):
        self._populate(engine, 300)
        start = time.perf_counter()
        for _ in range(20):
            engine.query_rows("SELECT SUM(value), AVG(value) FROM perf")
        elapsed = time.perf_counter() - start
        print(f'{{"bench_metric": "ops_per_second", "test": "test_sum_avg_300_rows", "value": {20 / elapsed:.2f}, "iterations": 20, "duration_seconds": {elapsed:.6f}}}')

    def test_group_by_10_categories(self, engine):
        """GROUP BY with 10 distinct categories over 300 rows."""
        self._populate(engine, 300)
        start = time.perf_counter()
        for _ in range(20):
            rows = engine.query_rows(
                "SELECT category, COUNT(*), SUM(value) FROM perf GROUP BY category"
            )
            assert len(rows) == 10
        elapsed = time.perf_counter() - start
        print(f'{{"bench_metric": "ops_per_second", "test": "test_group_by_10_categories", "value": {20 / elapsed:.2f}, "iterations": 20, "duration_seconds": {elapsed:.6f}}}')
