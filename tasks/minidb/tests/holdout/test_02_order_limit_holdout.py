"""Stage 2 holdout tests: ORDER BY and LIMIT edge cases."""
import pytest


class TestCrossTypeOrderingEdge:
    def test_full_type_hierarchy(self, engine):
        """Test the complete cross-type ordering with all types."""
        engine.execute("CREATE TABLE t (a)")
        engine.execute("INSERT INTO t VALUES ([1, 2])")
        engine.execute("INSERT INTO t VALUES (ts'2025-01-01T00:00:00Z')")
        engine.execute("INSERT INTO t VALUES (42)")
        engine.execute("INSERT INTO t VALUES ('hello')")
        engine.execute("INSERT INTO t VALUES (null)")
        engine.execute("INSERT INTO t VALUES (true)")
        engine.execute("INSERT INTO t VALUES (x'ff' AS 'image/png')")
        engine.execute("INSERT INTO t VALUES (false)")
        rows = engine.query_rows("SELECT TYPEOF(a) FROM t ORDER BY a ASC")
        types = [r[0] for r in rows]
        assert types == ["null", "boolean", "boolean", "integer",
                        "string", "timestamp", "list", "blob"]

    def test_desc_reverses_cross_type(self, engine):
        engine.execute("CREATE TABLE t (a)")
        engine.execute("INSERT INTO t VALUES (null)")
        engine.execute("INSERT INTO t VALUES (42)")
        engine.execute("INSERT INTO t VALUES ('z')")
        rows = engine.query_rows("SELECT a FROM t ORDER BY a DESC")
        vals = [r[0] for r in rows]
        assert vals == ["z", 42, None]

    def test_list_lexicographic_order(self, engine):
        engine.execute("CREATE TABLE t (a)")
        engine.execute("INSERT INTO t VALUES ([1, 3])")
        engine.execute("INSERT INTO t VALUES ([1, 2])")
        engine.execute("INSERT INTO t VALUES ([2, 1])")
        rows = engine.query_rows("SELECT a FROM t ORDER BY a ASC")
        vals = [r[0] for r in rows]
        assert vals == [[1, 2], [1, 3], [2, 1]]

    def test_order_by_typeof(self, engine):
        """ORDER BY on TYPEOF expression."""
        engine.execute("CREATE TABLE t (a)")
        engine.execute("INSERT INTO t VALUES (1)")
        engine.execute("INSERT INTO t VALUES ('x')")
        engine.execute("INSERT INTO t VALUES (true)")
        rows = engine.query_rows("SELECT a, TYPEOF(a) FROM t ORDER BY TYPEOF(a)")
        types = [r[1] for r in rows]
        assert types == sorted(types)

    def test_limit_zero(self, engine):
        engine.execute("CREATE TABLE t (a)")
        engine.execute("INSERT INTO t VALUES (1), (2)")
        rows = engine.query_rows("SELECT a FROM t LIMIT 0")
        assert rows == []

    def test_order_by_mixed_numbers(self, engine):
        """Ints and floats should interleave correctly."""
        engine.execute("CREATE TABLE t (a)")
        engine.execute("INSERT INTO t VALUES (3)")
        engine.execute("INSERT INTO t VALUES (1.5)")
        engine.execute("INSERT INTO t VALUES (2)")
        engine.execute("INSERT INTO t VALUES (1.0)")
        rows = engine.query_rows("SELECT a FROM t ORDER BY a")
        vals = [r[0] for r in rows]
        assert vals == [1.0, 1.5, 2, 3]

    def test_order_by_secondary_key_different_type(self, engine):
        """Multi-key sort where secondary key has mixed types."""
        engine.execute("CREATE TABLE t (grp, val)")
        engine.execute("INSERT INTO t VALUES (1, 'b')")
        engine.execute("INSERT INTO t VALUES (1, 10)")
        engine.execute("INSERT INTO t VALUES (2, 'a')")
        rows = engine.query_rows("SELECT grp, val FROM t ORDER BY grp ASC, val ASC")
        # group 1: 10 (number) < 'b' (string) in cross-type
        assert rows == [[1, 10], [1, "b"], [2, "a"]]
