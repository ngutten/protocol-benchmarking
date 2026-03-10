"""Performance benchmarks for Stage 2: ORDER BY / LIMIT.

Holdout — never provided to the LLM.
"""
import time


class TestOrderByPerf:
    def _populate(self, engine, n=300):
        engine.execute("CREATE TABLE perf (id, name, score)")
        for i in range(n):
            engine.execute(f"INSERT INTO perf VALUES ({i}, 'user_{i}', {(i * 37) % 1000})")

    def test_order_by_300_rows(self, engine):
        """Sort 300 rows by a numeric column."""
        self._populate(engine, 300)
        start = time.perf_counter()
        for _ in range(20):
            engine.query_rows("SELECT * FROM perf ORDER BY score")
        elapsed = time.perf_counter() - start
        print(f'{{"bench_metric": "ops_per_second", "test": "test_order_by_300_rows", "value": {20 / elapsed:.2f}, "iterations": 20, "duration_seconds": {elapsed:.6f}}}')

    def test_order_by_desc_300_rows(self, engine):
        """Sort 300 rows descending."""
        self._populate(engine, 300)
        start = time.perf_counter()
        for _ in range(20):
            engine.query_rows("SELECT * FROM perf ORDER BY score DESC")
        elapsed = time.perf_counter() - start
        print(f'{{"bench_metric": "ops_per_second", "test": "test_order_by_desc_300_rows", "value": {20 / elapsed:.2f}, "iterations": 20, "duration_seconds": {elapsed:.6f}}}')

    def test_limit_from_large_table(self, engine):
        """LIMIT 10 from 300-row table."""
        self._populate(engine, 300)
        start = time.perf_counter()
        for _ in range(40):
            rows = engine.query_rows("SELECT * FROM perf ORDER BY score LIMIT 10")
            assert len(rows) == 10
        elapsed = time.perf_counter() - start
        print(f'{{"bench_metric": "ops_per_second", "test": "test_limit_from_large_table", "value": {40 / elapsed:.2f}, "iterations": 40, "duration_seconds": {elapsed:.6f}}}')

    def test_order_limit_offset(self, engine):
        """ORDER BY + LIMIT + OFFSET on 300 rows."""
        self._populate(engine, 300)
        start = time.perf_counter()
        for _ in range(40):
            rows = engine.query_rows("SELECT * FROM perf ORDER BY score LIMIT 10 OFFSET 50")
            assert len(rows) == 10
        elapsed = time.perf_counter() - start
        print(f'{{"bench_metric": "ops_per_second", "test": "test_order_limit_offset", "value": {40 / elapsed:.2f}, "iterations": 40, "duration_seconds": {elapsed:.6f}}}')
