"""Stage 3 training tests: Aggregation and GROUP BY."""
import pytest


class TestBasicAggregation:
    def test_count_star(self, engine):
        engine.execute("CREATE TABLE t (a)")
        engine.execute("INSERT INTO t VALUES (1), (2), (3)")
        val = engine.query_scalar("SELECT COUNT(*) FROM t")
        assert val == 3

    def test_count_expr(self, engine):
        engine.execute("CREATE TABLE t (a)")
        engine.execute("INSERT INTO t VALUES (1), (null), (3)")
        val = engine.query_scalar("SELECT COUNT(a) FROM t")
        assert val == 2

    def test_sum_numeric(self, engine):
        engine.execute("CREATE TABLE t (a)")
        engine.execute("INSERT INTO t VALUES (1), (2), (3)")
        val = engine.query_scalar("SELECT SUM(a) FROM t")
        assert val == 6

    def test_avg_numeric(self, engine):
        engine.execute("CREATE TABLE t (a)")
        engine.execute("INSERT INTO t VALUES (10), (20), (30)")
        val = engine.query_scalar("SELECT AVG(a) FROM t")
        assert val == 20.0

    def test_min_max_numeric(self, engine):
        engine.execute("CREATE TABLE t (a)")
        engine.execute("INSERT INTO t VALUES (3), (1), (2)")
        assert engine.query_scalar("SELECT MIN(a) FROM t") == 1
        assert engine.query_scalar("SELECT MAX(a) FROM t") == 3


class TestGroupBy:
    def test_group_by_basic(self, engine):
        engine.execute("CREATE TABLE t (grp, val)")
        engine.execute("INSERT INTO t VALUES (\'a\', 1), (\'b\', 2), (\'a\', 3)")
        rows = engine.query_rows("SELECT grp, SUM(val) FROM t GROUP BY grp ORDER BY grp")
        assert rows == [["a", 4], ["b", 2]]

    def test_group_by_count(self, engine):
        engine.execute("CREATE TABLE t (grp, val)")
        engine.execute("INSERT INTO t VALUES (\'a\', 1), (\'b\', 2), (\'a\', 3), (\'a\', null)")
        rows = engine.query_rows(
            "SELECT grp, COUNT(*), COUNT(val) FROM t GROUP BY grp ORDER BY grp"
        )
        assert rows == [["a", 3, 2], ["b", 1, 1]]

    def test_group_by_with_where(self, engine):
        engine.execute("CREATE TABLE t (grp, val)")
        engine.execute("INSERT INTO t VALUES (\'a\', 1), (\'b\', 2), (\'a\', 3), (\'b\', 4)")
        rows = engine.query_rows(
            "SELECT grp, SUM(val) FROM t WHERE val > 1 GROUP BY grp ORDER BY grp"
        )
        assert rows == [["a", 3], ["b", 6]]


class TestAggregateMode:
    def test_set_aggregate_mode(self, engine):
        engine.execute("CREATE TABLE t (a)")
        resp = engine.execute("SET AGGREGATE_MODE = \'strict\'")
        assert resp["ok"] is True

    def test_lenient_sum_mixed(self, engine):
        engine.execute("CREATE TABLE t (a)")
        engine.execute("INSERT INTO t VALUES (10), (\'hello\'), (20), (true)")
        val = engine.query_scalar("SELECT SUM(a) FROM t")
        assert val == 31

    def test_strict_sum_mixed_error(self, engine):
        engine.execute("CREATE TABLE t (a)")
        engine.execute("INSERT INTO t VALUES (10), (\'hello\'), (20)")
        engine.execute("SET AGGREGATE_MODE = \'strict\'")
        engine.expect_error("SELECT SUM(a) FROM t")

    def test_lenient_min_cross_type(self, engine):
        engine.execute("CREATE TABLE t (a)")
        engine.execute("INSERT INTO t VALUES (42), (\'hello\'), (null), (true)")
        val = engine.query_scalar("SELECT MIN(a) FROM t")
        assert val is None

    def test_lenient_avg_all_non_numeric(self, engine):
        engine.execute("CREATE TABLE t (a)")
        engine.execute("INSERT INTO t VALUES (\'x\'), (\'y\')")
        val = engine.query_scalar("SELECT AVG(a) FROM t")
        assert val is None

    def test_empty_table_aggregation(self, engine):
        engine.execute("CREATE TABLE t (a)")
        val = engine.query_scalar("SELECT COUNT(*) FROM t")
        assert val == 0
