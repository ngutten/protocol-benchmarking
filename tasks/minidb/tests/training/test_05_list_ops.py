"""Stage 5 training tests: List operations (CONTAINS, FLATTEN)."""
import pytest


class TestContains:
    def test_contains_basic(self, engine):
        engine.execute("CREATE TABLE t (id, tags)")
        engine.execute("INSERT INTO t VALUES (1, [1, 2, 3])")
        engine.execute("INSERT INTO t VALUES (2, [4, 5, 6])")
        rows = engine.query_rows("SELECT id FROM t WHERE tags CONTAINS 2")
        assert rows == [[1]]

    def test_contains_string(self, engine):
        engine.execute("CREATE TABLE t (id, tags)")
        engine.execute("INSERT INTO t VALUES (1, ['a', 'b', 'c'])")
        rows = engine.query_rows("SELECT id FROM t WHERE tags CONTAINS 'b'")
        assert rows == [[1]]

    def test_contains_with_coercion(self, engine):
        """[1, 2, 3] CONTAINS '2' should be true (string coerces to int)."""
        engine.execute("CREATE TABLE t (id, tags)")
        engine.execute("INSERT INTO t VALUES (1, [1, 2, 3])")
        rows = engine.query_rows("SELECT id FROM t WHERE tags CONTAINS '2'")
        assert rows == [[1]]

    def test_contains_non_list_returns_false(self, engine):
        engine.execute("CREATE TABLE t (id, val)")
        engine.execute("INSERT INTO t VALUES (1, 42)")
        engine.execute("INSERT INTO t VALUES (2, [42])")
        rows = engine.query_rows("SELECT id FROM t WHERE val CONTAINS 42")
        assert rows == [[2]]  # only the list row matches

    def test_contains_null_returns_null(self, engine):
        engine.execute("CREATE TABLE t (id, val)")
        engine.execute("INSERT INTO t VALUES (1, null)")
        rows = engine.query_rows("SELECT id FROM t WHERE val CONTAINS 1")
        assert rows == []


class TestFlatten:
    def test_flatten_basic(self, engine):
        engine.execute("CREATE TABLE t (id, tags)")
        engine.execute("INSERT INTO t VALUES (1, ['a', 'b', 'c'])")
        engine.execute("INSERT INTO t VALUES (2, ['d'])")
        rows = engine.query_rows("SELECT id, FLATTEN(tags) AS tag FROM t ORDER BY tag")
        assert rows == [[1, "a"], [1, "b"], [1, "c"], [2, "d"]]

    def test_flatten_non_list_passthrough(self, engine):
        engine.execute("CREATE TABLE t (id, val)")
        engine.execute("INSERT INTO t VALUES (1, 'single')")
        rows = engine.query_rows("SELECT id, FLATTEN(val) AS v FROM t")
        assert rows == [[1, "single"]]

    def test_flatten_null(self, engine):
        engine.execute("CREATE TABLE t (id, val)")
        engine.execute("INSERT INTO t VALUES (1, null)")
        rows = engine.query_rows("SELECT id, FLATTEN(val) AS v FROM t")
        assert rows == [[1, None]]

    def test_flatten_nested_one_level(self, engine):
        """FLATTEN only expands one level."""
        engine.execute("CREATE TABLE t (id, val)")
        engine.execute("INSERT INTO t VALUES (1, [1, [2, 3]])")
        rows = engine.query_rows("SELECT id, FLATTEN(val) AS v FROM t ORDER BY id")
        assert rows == [[1, 1], [1, [2, 3]]]

    def test_flatten_with_where(self, engine):
        """WHERE is applied before FLATTEN."""
        engine.execute("CREATE TABLE t (id, tags)")
        engine.execute("INSERT INTO t VALUES (1, ['a', 'b'])")
        engine.execute("INSERT INTO t VALUES (2, ['c', 'd'])")
        rows = engine.query_rows(
            "SELECT id, FLATTEN(tags) AS tag FROM t WHERE id = 1"
        )
        assert len(rows) == 2
        assert all(r[0] == 1 for r in rows)
