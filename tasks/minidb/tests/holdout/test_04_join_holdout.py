"""Stage 4 holdout: JOIN edge cases."""
import pytest


class TestJoinEdgeCases:
    def test_join_with_where(self, engine):
        engine.execute("CREATE TABLE t1 (id, val)")
        engine.execute("CREATE TABLE t2 (id, val)")
        engine.execute("INSERT INTO t1 VALUES (1, 10), (2, 20)")
        engine.execute("INSERT INTO t2 VALUES (1, 100), (2, 200)")
        rows = engine.query_rows(
            "SELECT t1.val, t2.val FROM t1 JOIN t2 ON t1.id = t2.id WHERE t1.val > 15"
        )
        assert rows == [[20, 200]]

    def test_join_with_aggregation(self, engine):
        engine.execute("CREATE TABLE t1 (id, grp)")
        engine.execute("CREATE TABLE t2 (id, val)")
        engine.execute("INSERT INTO t1 VALUES (1, 'a'), (2, 'a'), (3, 'b')")
        engine.execute("INSERT INTO t2 VALUES (1, 10), (2, 20), (3, 30)")
        rows = engine.query_rows(
            "SELECT t1.grp, SUM(t2.val) FROM t1 JOIN t2 ON t1.id = t2.id GROUP BY t1.grp ORDER BY t1.grp"
        )
        assert rows == [["a", 30], ["b", 30]]

    def test_join_null_in_condition(self, engine):
        """Null in join condition should not match anything (three-valued)."""
        engine.execute("CREATE TABLE t1 (id, val)")
        engine.execute("CREATE TABLE t2 (id, val)")
        engine.execute("INSERT INTO t1 VALUES (null, 'a')")
        engine.execute("INSERT INTO t2 VALUES (null, 'b')")
        rows = engine.query_rows(
            "SELECT t1.val FROM t1 JOIN t2 ON t1.id = t2.id"
        )
        assert rows == []  # null = null yields null, not true

    def test_join_many_to_many(self, engine):
        engine.execute("CREATE TABLE t1 (k, v1)")
        engine.execute("CREATE TABLE t2 (k, v2)")
        engine.execute("INSERT INTO t1 VALUES (1, 'a'), (1, 'b')")
        engine.execute("INSERT INTO t2 VALUES (1, 'x'), (1, 'y')")
        rows = engine.query_rows(
            "SELECT v1, v2 FROM t1 JOIN t2 ON t1.k = t2.k ORDER BY v1, v2"
        )
        assert len(rows) == 4  # cartesian product within matching key
        assert rows == [["a", "x"], ["a", "y"], ["b", "x"], ["b", "y"]]

    def test_join_with_expression_in_on(self, engine):
        engine.execute("CREATE TABLE t1 (a)")
        engine.execute("CREATE TABLE t2 (b)")
        engine.execute("INSERT INTO t1 VALUES (1), (2), (3)")
        engine.execute("INSERT INTO t2 VALUES (2), (4), (6)")
        rows = engine.query_rows(
            "SELECT t1.a, t2.b FROM t1 JOIN t2 ON t1.a * 2 = t2.b ORDER BY t1.a"
        )
        assert rows == [[1, 2], [2, 4], [3, 6]]

    def test_ambiguous_column_error(self, engine):
        engine.execute("CREATE TABLE t1 (id, val)")
        engine.execute("CREATE TABLE t2 (id, val)")
        engine.execute("INSERT INTO t1 VALUES (1, 'a')")
        engine.execute("INSERT INTO t2 VALUES (1, 'b')")
        # Unqualified 'id' is ambiguous
        engine.expect_error(
            "SELECT id FROM t1 JOIN t2 ON t1.id = t2.id"
        )

    def test_unambiguous_column_resolves(self, engine):
        engine.execute("CREATE TABLE t1 (id, name)")
        engine.execute("CREATE TABLE t2 (id, score)")
        engine.execute("INSERT INTO t1 VALUES (1, 'alice')")
        engine.execute("INSERT INTO t2 VALUES (1, 95)")
        rows = engine.query_rows(
            "SELECT name, score FROM t1 JOIN t2 ON t1.id = t2.id"
        )
        assert rows == [["alice", 95]]
