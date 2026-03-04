"""Stage 2 training tests: ORDER BY and LIMIT."""
import pytest


class TestOrderBy:
    def test_order_by_numeric_asc(self, engine):
        engine.execute("CREATE TABLE t (a)")
        engine.execute("INSERT INTO t VALUES (3), (1), (2)")
        rows = engine.query_rows("SELECT a FROM t ORDER BY a ASC")
        assert [r[0] for r in rows] == [1, 2, 3]

    def test_order_by_numeric_desc(self, engine):
        engine.execute("CREATE TABLE t (a)")
        engine.execute("INSERT INTO t VALUES (3), (1), (2)")
        rows = engine.query_rows("SELECT a FROM t ORDER BY a DESC")
        assert [r[0] for r in rows] == [3, 2, 1]

    def test_order_by_string(self, engine):
        engine.execute("CREATE TABLE t (a)")
        engine.execute("INSERT INTO t VALUES ('banana'), ('apple'), ('cherry')")
        rows = engine.query_rows("SELECT a FROM t ORDER BY a")
        assert [r[0] for r in rows] == ["apple", "banana", "cherry"]

    def test_order_by_default_asc(self, engine):
        engine.execute("CREATE TABLE t (a)")
        engine.execute("INSERT INTO t VALUES (3), (1), (2)")
        rows = engine.query_rows("SELECT a FROM t ORDER BY a")
        assert [r[0] for r in rows] == [1, 2, 3]

    def test_order_by_multiple_keys(self, engine):
        engine.execute("CREATE TABLE t (a, b)")
        engine.execute("INSERT INTO t VALUES (1, 'z'), (2, 'a'), (1, 'a')")
        rows = engine.query_rows("SELECT a, b FROM t ORDER BY a ASC, b ASC")
        assert rows == [[1, "a"], [1, "z"], [2, "a"]]

    def test_cross_type_ordering(self, engine):
        """NULL < bool < number < string per spec."""
        engine.execute("CREATE TABLE t (a)")
        engine.execute("INSERT INTO t VALUES ('hello')")
        engine.execute("INSERT INTO t VALUES (42)")
        engine.execute("INSERT INTO t VALUES (null)")
        engine.execute("INSERT INTO t VALUES (true)")
        engine.execute("INSERT INTO t VALUES (false)")
        rows = engine.query_rows("SELECT a FROM t ORDER BY a ASC")
        vals = [r[0] for r in rows]
        assert vals == [None, False, True, 42, "hello"]

    def test_order_by_with_where(self, engine):
        engine.execute("CREATE TABLE t (a)")
        engine.execute("INSERT INTO t VALUES (3), (1), (2), (5), (4)")
        rows = engine.query_rows("SELECT a FROM t WHERE a > 2 ORDER BY a DESC")
        assert [r[0] for r in rows] == [5, 4, 3]


class TestLimit:
    def test_limit(self, engine):
        engine.execute("CREATE TABLE t (a)")
        engine.execute("INSERT INTO t VALUES (1), (2), (3), (4), (5)")
        rows = engine.query_rows("SELECT a FROM t ORDER BY a LIMIT 3")
        assert [r[0] for r in rows] == [1, 2, 3]

    def test_limit_without_order(self, engine):
        engine.execute("CREATE TABLE t (a)")
        engine.execute("INSERT INTO t VALUES (1), (2), (3)")
        rows = engine.query_rows("SELECT a FROM t LIMIT 2")
        assert len(rows) == 2

    def test_limit_larger_than_rows(self, engine):
        engine.execute("CREATE TABLE t (a)")
        engine.execute("INSERT INTO t VALUES (1), (2)")
        rows = engine.query_rows("SELECT a FROM t ORDER BY a LIMIT 100")
        assert [r[0] for r in rows] == [1, 2]

    def test_order_by_expression(self, engine):
        engine.execute("CREATE TABLE t (a, b)")
        engine.execute("INSERT INTO t VALUES (1, 10), (2, 5), (3, 8)")
        rows = engine.query_rows("SELECT a FROM t ORDER BY a + b DESC")
        assert rows[2] == [2]  # smallest sum (7) last
