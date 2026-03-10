"""Performance benchmarks for Stage 4: JOIN.

Holdout — never provided to the LLM.
"""
import time


class TestJoinPerf:
    def _populate(self, engine, n_left=100, n_right=50):
        engine.execute("CREATE TABLE left_t (id, value)")
        engine.execute("CREATE TABLE right_t (id, label)")
        for i in range(n_left):
            engine.execute(f"INSERT INTO left_t VALUES ({i}, {i * 10})")
        for i in range(n_right):
            engine.execute(f"INSERT INTO right_t VALUES ({i}, 'label_{i}')")

    def test_inner_join_100x50(self, engine):
        """INNER JOIN between 100-row and 50-row tables."""
        self._populate(engine, 100, 50)
        start = time.perf_counter()
        for _ in range(20):
            rows = engine.query_rows(
                "SELECT left_t.id, value, label FROM left_t JOIN right_t ON left_t.id = right_t.id"
            )
            assert len(rows) == 50
        elapsed = time.perf_counter() - start
        print(f'{{"bench_metric": "ops_per_second", "test": "test_inner_join_100x50", "value": {20 / elapsed:.2f}, "iterations": 20, "duration_seconds": {elapsed:.6f}}}')

    def test_join_with_where(self, engine):
        """JOIN + WHERE filter."""
        self._populate(engine, 100, 50)
        start = time.perf_counter()
        for _ in range(20):
            engine.query_rows(
                "SELECT left_t.id, value FROM left_t JOIN right_t ON left_t.id = right_t.id WHERE value > 200"
            )
        elapsed = time.perf_counter() - start
        print(f'{{"bench_metric": "ops_per_second", "test": "test_join_with_where", "value": {20 / elapsed:.2f}, "iterations": 20, "duration_seconds": {elapsed:.6f}}}')
