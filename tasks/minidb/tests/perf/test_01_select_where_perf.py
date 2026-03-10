"""Performance benchmarks for Stage 1: SELECT / WHERE.

These are holdout tests — never provided to the LLM.
Each test exercises a workload and is timed automatically by the harness.
"""
import time


class TestInsertThroughput:
    def test_bulk_insert_100_rows(self, engine):
        """Measure INSERT throughput with 100 rows."""
        engine.execute("CREATE TABLE perf (id, name, value)")
        start = time.perf_counter()
        for i in range(200):
            engine.execute(f"INSERT INTO perf VALUES ({i}, 'user_{i}', {i * 1.5})")
        elapsed = time.perf_counter() - start
        # Verify data landed
        rows = engine.query_rows("SELECT COUNT(*) FROM perf")
        assert rows[0][0] == 200
        # Print machine-readable metric
        print(f'{{"bench_metric": "ops_per_second", "test": "test_bulk_insert_100_rows", "value": {200 / elapsed:.2f}, "iterations": 200, "duration_seconds": {elapsed:.6f}}}')

    def test_bulk_insert_500_rows(self, engine):
        """Measure INSERT throughput with 500 rows."""
        engine.execute("CREATE TABLE perf (id, name, value)")
        start = time.perf_counter()
        for i in range(1000):
            engine.execute(f"INSERT INTO perf VALUES ({i}, 'user_{i}', {i * 1.5})")
        elapsed = time.perf_counter() - start
        rows = engine.query_rows("SELECT COUNT(*) FROM perf")
        assert rows[0][0] == 1000
        print(f'{{"bench_metric": "ops_per_second", "test": "test_bulk_insert_500_rows", "value": {1000 / elapsed:.2f}, "iterations": 1000, "duration_seconds": {elapsed:.6f}}}')


class TestSelectThroughput:
    def _populate(self, engine, n=200):
        engine.execute("CREATE TABLE perf (id, name, value, flag)")
        for i in range(n):
            flag = "true" if i % 2 == 0 else "false"
            engine.execute(f"INSERT INTO perf VALUES ({i}, 'user_{i}', {i * 1.1}, {flag})")

    def test_select_star_200_rows(self, engine):
        """Full table scan on 200 rows."""
        self._populate(engine, 200)
        start = time.perf_counter()
        for _ in range(20):
            engine.query_rows("SELECT * FROM perf")
        elapsed = time.perf_counter() - start
        print(f'{{"bench_metric": "ops_per_second", "test": "test_select_star_200_rows", "value": {20 / elapsed:.2f}, "iterations": 20, "duration_seconds": {elapsed:.6f}}}')

    def test_where_filter_200_rows(self, engine):
        """WHERE filter on 200 rows, repeated."""
        self._populate(engine, 200)
        start = time.perf_counter()
        for _ in range(20):
            engine.query_rows("SELECT id, name FROM perf WHERE value > 100")
        elapsed = time.perf_counter() - start
        print(f'{{"bench_metric": "ops_per_second", "test": "test_where_filter_200_rows", "value": {20 / elapsed:.2f}, "iterations": 20, "duration_seconds": {elapsed:.6f}}}')

    def test_compound_where_200_rows(self, engine):
        """Compound WHERE with AND/OR on 200 rows."""
        self._populate(engine, 200)
        start = time.perf_counter()
        for _ in range(20):
            engine.query_rows("SELECT id FROM perf WHERE value > 50 AND flag = true")
        elapsed = time.perf_counter() - start
        print(f'{{"bench_metric": "ops_per_second", "test": "test_compound_where_200_rows", "value": {20 / elapsed:.2f}, "iterations": 20, "duration_seconds": {elapsed:.6f}}}')
