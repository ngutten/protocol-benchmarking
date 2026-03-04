"""Stage 5 holdout: list operations edge cases."""
import pytest


class TestContainsEdge:
    def test_contains_in_join_condition(self, engine):
        engine.execute("CREATE TABLE items (id, tags)")
        engine.execute("CREATE TABLE filters (tag)")
        engine.execute("INSERT INTO items VALUES (1, ['red', 'blue']), (2, ['green'])")
        engine.execute("INSERT INTO filters VALUES ('blue'), ('green')")
        rows = engine.query_rows(
            "SELECT items.id, filters.tag FROM items JOIN filters ON items.tags CONTAINS filters.tag ORDER BY items.id, filters.tag"
        )
        assert rows == [[1, "blue"], [2, "green"]]

    def test_contains_boolean_in_list(self, engine):
        engine.execute("CREATE TABLE t (id, vals)")
        engine.execute("INSERT INTO t VALUES (1, [true, false, 1])")
        # CONTAINS true: true is in the list
        rows = engine.query_rows("SELECT id FROM t WHERE vals CONTAINS true")
        assert rows == [[1]]

    def test_contains_empty_list(self, engine):
        engine.execute("CREATE TABLE t (id, tags)")
        engine.execute("INSERT INTO t VALUES (1, [])")
        rows = engine.query_rows("SELECT id FROM t WHERE tags CONTAINS 'x'")
        assert rows == []


class TestFlattenEdge:
    def test_flatten_empty_list(self, engine):
        """Empty list produces zero rows for that input row."""
        engine.execute("CREATE TABLE t (id, val)")
        engine.execute("INSERT INTO t VALUES (1, [])")
        engine.execute("INSERT INTO t VALUES (2, [10])")
        rows = engine.query_rows("SELECT id, FLATTEN(val) AS v FROM t")
        assert rows == [[2, 10]]

    def test_flatten_with_group_by(self, engine):
        engine.execute("CREATE TABLE t (grp, items)")
        engine.execute("INSERT INTO t VALUES ('a', [1, 2, 3])")
        engine.execute("INSERT INTO t VALUES ('b', [4, 5])")
        rows = engine.query_rows(
            "SELECT grp, COUNT(*) FROM (SELECT grp, FLATTEN(items) AS item FROM t) GROUP BY grp ORDER BY grp"
        )
        # Hmm, subqueries aren't in scope. Let me do this differently.
        # FLATTEN + GROUP BY on the flattened column
        engine.execute("CREATE TABLE t2 (id, tags)")
        engine.execute("INSERT INTO t2 VALUES (1, ['a', 'b'])")
        engine.execute("INSERT INTO t2 VALUES (2, ['a', 'c'])")
        rows = engine.query_rows(
            "SELECT FLATTEN(tags) AS tag, COUNT(*) FROM t2 GROUP BY tag ORDER BY tag"
        )
        assert rows == [["a", 2], ["b", 1], ["c", 1]]

    def test_flatten_with_order_by_and_limit(self, engine):
        engine.execute("CREATE TABLE t (id, vals)")
        engine.execute("INSERT INTO t VALUES (1, [30, 10, 20])")
        rows = engine.query_rows(
            "SELECT FLATTEN(vals) AS v FROM t ORDER BY v ASC LIMIT 2"
        )
        assert rows == [[10], [20]]

    def test_flatten_preserves_other_columns(self, engine):
        engine.execute("CREATE TABLE t (id, name, tags)")
        engine.execute("INSERT INTO t VALUES (1, 'alice', ['x', 'y'])")
        rows = engine.query_rows(
            "SELECT id, name, FLATTEN(tags) AS tag FROM t ORDER BY tag"
        )
        assert rows == [[1, "alice", "x"], [1, "alice", "y"]]

    def test_flatten_mixed_types_in_list(self, engine):
        engine.execute("CREATE TABLE t (id, data)")
        engine.execute("INSERT INTO t VALUES (1, [1, 'two', true, null])")
        rows = engine.query_rows("SELECT FLATTEN(data) AS d FROM t")
        vals = [r[0] for r in rows]
        assert vals == [1, "two", True, None]
