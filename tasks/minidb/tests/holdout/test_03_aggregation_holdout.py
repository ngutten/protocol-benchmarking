"""Stage 3 holdout: aggregation edge cases."""
import pytest


class TestAggregationEdgeCases:
    def test_sum_empty_group(self, engine):
        engine.execute("CREATE TABLE t (grp, val)")
        engine.execute("INSERT INTO t VALUES ('a', 1)")
        rows = engine.query_rows("SELECT grp, SUM(val) FROM t WHERE grp = 'b' GROUP BY grp")
        assert rows == []

    def test_sum_all_nulls(self, engine):
        engine.execute("CREATE TABLE t (a)")
        engine.execute("INSERT INTO t VALUES (null), (null)")
        val = engine.query_scalar("SELECT SUM(a) FROM t")
        assert val is None

    def test_avg_int_returns_float(self, engine):
        engine.execute("CREATE TABLE t (a)")
        engine.execute("INSERT INTO t VALUES (1), (2)")
        val = engine.query_scalar("SELECT AVG(a) FROM t")
        assert val == 1.5
        assert isinstance(val, float)

    def test_max_cross_type_lenient(self, engine):
        engine.execute("CREATE TABLE t (a)")
        engine.execute("INSERT INTO t VALUES (1)")
        engine.execute("INSERT INTO t VALUES ('z')")
        engine.execute("INSERT INTO t VALUES (true)")
        val = engine.query_scalar("SELECT MAX(a) FROM t")
        assert val == "z"  # string > number > bool in cross-type

    def test_strict_mode_sum_with_booleans(self, engine):
        """In strict mode, booleans in SUM should error (non-numeric)."""
        engine.execute("CREATE TABLE t (a)")
        engine.execute("INSERT INTO t VALUES (1), (true), (3)")
        engine.execute("SET AGGREGATE_MODE = 'strict'")
        engine.expect_error("SELECT SUM(a) FROM t")

    def test_group_by_with_order_by_aggregate(self, engine):
        engine.execute("CREATE TABLE t (grp, val)")
        engine.execute("INSERT INTO t VALUES ('a', 10), ('b', 5), ('c', 20)")
        rows = engine.query_rows(
            "SELECT grp, SUM(val) FROM t GROUP BY grp ORDER BY SUM(val) DESC"
        )
        assert rows[0] == ["c", 20]
        assert rows[2] == ["b", 5]

    def test_group_by_null_values(self, engine):
        """Rows with null group key form their own group."""
        engine.execute("CREATE TABLE t (grp, val)")
        engine.execute("INSERT INTO t VALUES ('a', 1), (null, 2), ('a', 3), (null, 4)")
        rows = engine.query_rows(
            "SELECT grp, SUM(val) FROM t GROUP BY grp ORDER BY grp"
        )
        # null group comes first in cross-type ordering
        assert rows[0] == [None, 6]
        assert rows[1] == ["a", 4]

    def test_count_star_vs_count_expr_with_nulls(self, engine):
        engine.execute("CREATE TABLE t (a)")
        engine.execute("INSERT INTO t VALUES (1), (null), (null)")
        star = engine.query_scalar("SELECT COUNT(*) FROM t")
        expr = engine.query_scalar("SELECT COUNT(a) FROM t")
        assert star == 3
        assert expr == 1

    def test_group_by_with_limit(self, engine):
        engine.execute("CREATE TABLE t (grp, val)")
        engine.execute("INSERT INTO t VALUES ('a', 1), ('b', 2), ('c', 3)")
        rows = engine.query_rows(
            "SELECT grp, SUM(val) FROM t GROUP BY grp ORDER BY grp LIMIT 2"
        )
        assert len(rows) == 2
        assert rows[0][0] == "a"

    def test_lenient_sum_with_blobs(self, engine):
        """Blobs in SUM should be skipped in lenient mode."""
        engine.execute("CREATE TABLE t (a)")
        engine.execute("INSERT INTO t VALUES (10)")
        engine.execute("INSERT INTO t VALUES (x'ff' AS 'image/png')")
        engine.execute("INSERT INTO t VALUES (20)")
        val = engine.query_scalar("SELECT SUM(a) FROM t")
        assert val == 30
