"""Performance benchmarks for Stage 5: List operations.

Holdout — never provided to the LLM.
"""
import time


class TestListOpsPerf:
    def _populate(self, engine, n=100):
        engine.execute("CREATE TABLE perf (id, items)")
        for i in range(n):
            items = [j for j in range(i % 10)]
            engine.execute(f"INSERT INTO perf VALUES ({i}, {items})")

    def test_list_insert_and_select_100(self, engine):
        """Insert and retrieve 100 rows with list values."""
        engine.execute("CREATE TABLE perf (id, items)")
        start = time.perf_counter()
        for i in range(200):
            items = list(range(i % 10))
            engine.execute(f"INSERT INTO perf VALUES ({i}, {items})")
        for _ in range(10):
            engine.query_rows("SELECT * FROM perf")
        elapsed = time.perf_counter() - start
        print(f'{{"bench_metric": "ops_per_second", "test": "test_list_insert_and_select_100", "value": {210 / elapsed:.2f}, "iterations": 210, "duration_seconds": {elapsed:.6f}}}')

    def test_list_length_filter(self, engine):
        """Filter by list length on 100 rows."""
        self._populate(engine, 100)
        start = time.perf_counter()
        for _ in range(20):
            engine.query_rows("SELECT id FROM perf WHERE LENGTH(items) > 5")
        elapsed = time.perf_counter() - start
        print(f'{{"bench_metric": "ops_per_second", "test": "test_list_length_filter", "value": {20 / elapsed:.2f}, "iterations": 20, "duration_seconds": {elapsed:.6f}}}')
