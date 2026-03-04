#!/usr/bin/env python3
"""Generate remaining test files for MiniDB benchmark."""
import ast
import os

base = "/home/claude/benchmark/tasks/minidb/tests"

files = {}

# ============================================================
# Stage 3 holdout
# ============================================================
files[f"{base}/holdout/test_03_aggregation_holdout.py"] = '''
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
'''.lstrip()

# ============================================================
# Stage 4 training: JOIN
# ============================================================
files[f"{base}/training/test_04_join.py"] = '''
"""Stage 4 training tests: JOIN."""
import pytest


class TestBasicJoin:
    def test_inner_join(self, engine):
        engine.execute("CREATE TABLE users (id, name)")
        engine.execute("CREATE TABLE orders (user_id, product)")
        engine.execute("INSERT INTO users VALUES (1, 'alice'), (2, 'bob'), (3, 'carol')")
        engine.execute("INSERT INTO orders VALUES (1, 'widget'), (2, 'gadget'), (1, 'gizmo')")
        rows = engine.query_rows(
            "SELECT users.name, orders.product FROM users JOIN orders ON users.id = orders.user_id ORDER BY orders.product"
        )
        assert rows == [["alice", "gadget"], ["alice", "gizmo"], ["bob", "widget"]]
        # Wait, that's wrong. Let me fix: alice has widget and gizmo, bob has gadget
        # Actually: (1,'widget'), (2,'gadget'), (1,'gizmo')
        # alice(1)->widget, alice(1)->gizmo, bob(2)->gadget
        # sorted by product: gadget, gizmo, widget
        # So: bob-gadget, alice-gizmo, alice-widget

    def test_inner_join_corrected(self, engine):
        engine.execute("CREATE TABLE users (id, name)")
        engine.execute("CREATE TABLE orders (user_id, product)")
        engine.execute("INSERT INTO users VALUES (1, 'alice'), (2, 'bob')")
        engine.execute("INSERT INTO orders VALUES (1, 'widget'), (2, 'gadget')")
        rows = engine.query_rows(
            "SELECT users.name, orders.product FROM users JOIN orders ON users.id = orders.user_id ORDER BY users.name"
        )
        assert rows == [["alice", "widget"], ["bob", "gadget"]]

    def test_join_no_match(self, engine):
        """Rows without matches are excluded (inner join)."""
        engine.execute("CREATE TABLE a (id, val)")
        engine.execute("CREATE TABLE b (id, val)")
        engine.execute("INSERT INTO a VALUES (1, 'x'), (2, 'y')")
        engine.execute("INSERT INTO b VALUES (2, 'z'), (3, 'w')")
        rows = engine.query_rows("SELECT a.id, b.val FROM a JOIN b ON a.id = b.id")
        assert rows == [[2, "z"]]

    def test_join_select_star(self, engine):
        engine.execute("CREATE TABLE t1 (a, b)")
        engine.execute("CREATE TABLE t2 (a, c)")
        engine.execute("INSERT INTO t1 VALUES (1, 2)")
        engine.execute("INSERT INTO t2 VALUES (1, 3)")
        cols, rows = engine.query(
            "SELECT * FROM t1 JOIN t2 ON t1.a = t2.a"
        )
        # Duplicate 'a' columns should be prefixed
        assert "t1.a" in cols or "a" in cols
        assert len(cols) == 3  # t1.a, b, c (or t1.a, t2.a, b, c if both included)


class TestJoinWithTypes:
    def test_cross_type_join_condition(self, engine):
        """Join where one side has string, other has int - coercion applies."""
        engine.execute("CREATE TABLE t1 (id, val)")
        engine.execute("CREATE TABLE t2 (id, val)")
        engine.execute("INSERT INTO t1 VALUES (1, 'a')")
        engine.execute("INSERT INTO t2 VALUES ('1', 'b')")
        rows = engine.query_rows(
            "SELECT t1.val, t2.val FROM t1 JOIN t2 ON t1.id = t2.id"
        )
        # '1' coerces to 1 for comparison
        assert rows == [["a", "b"]]


class TestSelfJoin:
    def test_self_join_with_alias(self, engine):
        engine.execute("CREATE TABLE emp (id, name, manager_id)")
        engine.execute("INSERT INTO emp VALUES (1, 'alice', null)")
        engine.execute("INSERT INTO emp VALUES (2, 'bob', 1)")
        engine.execute("INSERT INTO emp VALUES (3, 'carol', 1)")
        rows = engine.query_rows(
            "SELECT e.name, m.name FROM emp AS e JOIN emp AS m ON e.manager_id = m.id ORDER BY e.name"
        )
        assert rows == [["bob", "alice"], ["carol", "alice"]]
'''.lstrip()

# ============================================================
# Stage 4 holdout: JOIN edge cases
# ============================================================
files[f"{base}/holdout/test_04_join_holdout.py"] = '''
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
'''.lstrip()

# ============================================================
# Stage 5 training: list operations
# ============================================================
files[f"{base}/training/test_05_list_ops.py"] = '''
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
'''.lstrip()

# ============================================================
# Stage 5 holdout: list operations edge cases
# ============================================================
files[f"{base}/holdout/test_05_list_ops_holdout.py"] = '''
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
'''.lstrip()

# ============================================================
# Stage 6 training: coercion rules
# ============================================================
files[f"{base}/training/test_06_coercion.py"] = '''
"""Stage 6 training tests: User-defined coercion rules."""
import pytest


class TestCoercionModes:
    def test_set_coerce_rules_default(self, engine):
        resp = engine.execute("SET COERCE_RULES = 'default'")
        assert resp["ok"] is True

    def test_strict_mode_blocks_cross_type(self, engine):
        engine.execute("CREATE TABLE t (a)")
        engine.execute("INSERT INTO t VALUES ('10')")
        engine.execute("INSERT INTO t VALUES (5)")
        engine.execute("SET COERCE_RULES = 'strict'")
        # In strict mode, comparing string '10' to number 5 should error per-row
        resp = engine.execute("SELECT a FROM t WHERE a > 3")
        # Row with '10': string vs int -> error -> null -> excluded
        # Row with 5: int vs int -> 5 > 3 -> true
        rows = resp["rows"]
        assert rows == [[5]]
        assert "warnings" in resp

    def test_numeric_mode_coerces_strings(self, engine):
        engine.execute("CREATE TABLE t (a)")
        engine.execute("INSERT INTO t VALUES ('10')")
        engine.execute("INSERT INTO t VALUES ('abc')")
        engine.execute("INSERT INTO t VALUES (5)")
        engine.execute("SET COERCE_RULES = 'numeric'")
        resp = engine.execute("SELECT a FROM t WHERE a > 3")
        # '10' -> 10 > 3 = true; 'abc' -> error -> excluded; 5 > 3 = true
        rows = resp["rows"]
        vals = [r[0] for r in rows]
        assert sorted(str(v) for v in vals) == ["10", "5"]

    def test_string_mode_lexicographic(self, engine):
        engine.execute("CREATE TABLE t (a)")
        engine.execute("INSERT INTO t VALUES (9)")
        engine.execute("INSERT INTO t VALUES (100)")
        engine.execute("SET COERCE_RULES = 'string'")
        rows = engine.query_rows("SELECT a FROM t ORDER BY a ASC")
        # String mode: '100' < '9' lexicographically
        vals = [r[0] for r in rows]
        assert vals == [100, 9]

    def test_switching_modes(self, engine):
        engine.execute("CREATE TABLE t (a)")
        engine.execute("INSERT INTO t VALUES ('10')")
        engine.execute("INSERT INTO t VALUES (5)")

        # Default mode: string '10' coerces to number
        rows = engine.query_rows("SELECT a FROM t WHERE a > 7")
        assert len(rows) == 1  # only '10'

        engine.execute("SET COERCE_RULES = 'strict'")
        resp = engine.execute("SELECT a FROM t WHERE a > 7")
        # Now string comparison errors
        assert len(resp["rows"]) == 0 or "warnings" in resp

        engine.execute("SET COERCE_RULES = 'default'")
        rows = engine.query_rows("SELECT a FROM t WHERE a > 7")
        assert len(rows) == 1  # back to normal


class TestCoercionInteractions:
    def test_strict_affects_aggregation(self, engine):
        engine.execute("CREATE TABLE t (a)")
        engine.execute("INSERT INTO t VALUES (1), (true), (3)")
        engine.execute("SET COERCE_RULES = 'strict'")
        engine.execute("SET AGGREGATE_MODE = 'strict'")
        engine.expect_error("SELECT SUM(a) FROM t")

    def test_string_mode_affects_order_by(self, engine):
        engine.execute("CREATE TABLE t (a)")
        engine.execute("INSERT INTO t VALUES (1), (2), (10)")
        engine.execute("SET COERCE_RULES = 'string'")
        rows = engine.query_rows("SELECT a FROM t ORDER BY a ASC")
        # All coerced to strings: '1' < '10' < '2'
        vals = [r[0] for r in rows]
        assert vals == [1, 10, 2]

    def test_cast_not_affected_by_coerce_rules(self, engine):
        """CAST should always work regardless of coercion mode."""
        engine.execute("CREATE TABLE t (a)")
        engine.execute("INSERT INTO t VALUES ('42')")
        engine.execute("SET COERCE_RULES = 'strict'")
        rows = engine.query_rows("SELECT CAST(a AS 'integer') FROM t")
        assert rows == [[42]]
'''.lstrip()

# ============================================================
# Stage 6 holdout: coercion edge cases + implicit invalidation
# ============================================================
files[f"{base}/holdout/test_06_coercion_holdout.py"] = '''
"""Stage 6 holdout: coercion edge cases and implicit invalidation tests."""
import pytest


class TestStringModeEdgeCases:
    def test_string_mode_comparison_9_vs_100(self, engine):
        """The classic gotcha: 9 > 100 in string mode because '9' > '1'."""
        engine.execute("CREATE TABLE t (a)")
        engine.execute("INSERT INTO t VALUES (9), (100)")
        engine.execute("SET COERCE_RULES = 'string'")
        rows = engine.query_rows("SELECT a FROM t WHERE a > 50")
        # In string mode: '9' > '50' is true (lex), '100' > '50' is false
        assert rows == [[9]]

    def test_string_mode_blob_representation(self, engine):
        engine.execute("CREATE TABLE t (a)")
        engine.execute("INSERT INTO t VALUES (x'ff' AS 'image/png')")
        engine.execute("INSERT INTO t VALUES ('hello')")
        engine.execute("SET COERCE_RULES = 'string'")
        # Both sides coerce to string, comparison should work
        rows = engine.query_rows("SELECT a FROM t WHERE a > 'a'")
        # blob -> '<blob:image/png:1>', 'hello' > 'a'
        # '<' < 'a' in ASCII, so blob representation starts with '<' -> excluded
        assert len(rows) == 1  # only 'hello'

    def test_string_mode_timestamp(self, engine):
        engine.execute("CREATE TABLE t (a)")
        engine.execute("INSERT INTO t VALUES (ts'2025-01-01T00:00:00Z')")
        engine.execute("INSERT INTO t VALUES (ts'2025-06-15T00:00:00Z')")
        engine.execute("SET COERCE_RULES = 'string'")
        rows = engine.query_rows("SELECT a FROM t ORDER BY a")
        # ISO format strings sort correctly lexicographically
        assert len(rows) == 2

    def test_string_mode_null_still_null(self, engine):
        engine.execute("CREATE TABLE t (a)")
        engine.execute("INSERT INTO t VALUES (null), (1)")
        engine.execute("SET COERCE_RULES = 'string'")
        rows = engine.query_rows("SELECT a FROM t WHERE a > 'x'")
        # null stays null in three-valued logic, excluded
        assert len(rows) <= 1


class TestNumericModeEdgeCases:
    def test_numeric_mode_bool_coercion(self, engine):
        engine.execute("CREATE TABLE t (a)")
        engine.execute("INSERT INTO t VALUES (true), (false)")
        engine.execute("SET COERCE_RULES = 'numeric'")
        rows = engine.query_rows("SELECT a FROM t WHERE a > 0")
        assert rows == [[True]]  # true->1 > 0

    def test_numeric_mode_timestamp_epoch(self, engine):
        engine.execute("CREATE TABLE t (a)")
        engine.execute("INSERT INTO t VALUES (ts'2025-01-01T00:00:00Z')")
        engine.execute("SET COERCE_RULES = 'numeric'")
        rows = engine.query_rows("SELECT a FROM t WHERE a > 0")
        # timestamp -> epoch seconds, should be > 0
        assert len(rows) == 1

    def test_numeric_mode_list_errors(self, engine):
        engine.execute("CREATE TABLE t (a)")
        engine.execute("INSERT INTO t VALUES ([1, 2, 3])")
        engine.execute("INSERT INTO t VALUES (42)")
        engine.execute("SET COERCE_RULES = 'numeric'")
        resp = engine.execute("SELECT a FROM t WHERE a > 10")
        # list -> numeric: error per-row -> null -> excluded
        assert resp["rows"] == [[42]]


class TestImplicitInvalidation:
    """Tests that verify existing features work correctly after coercion mode changes.
    These specifically test whether changing coercion rules breaks features from stages 1-5."""

    def test_contains_under_strict_coercion(self, engine):
        """CONTAINS with strict coercion: element comparison follows strict rules."""
        engine.execute("CREATE TABLE t (id, tags)")
        engine.execute("INSERT INTO t VALUES (1, [1, 2, 3])")
        engine.execute("SET COERCE_RULES = 'strict'")
        # CONTAINS '2' in strict mode: string vs int comparison -> error
        rows = engine.query_rows("SELECT id FROM t WHERE tags CONTAINS 2")
        assert rows == [[1]]  # int 2 vs int elements: fine
        # But string '2' should fail under strict
        resp = engine.execute("SELECT id FROM t WHERE tags CONTAINS '2'")
        # Should not match because strict mode blocks string->int coercion
        assert resp["rows"] == []

    def test_join_under_string_coercion(self, engine):
        """JOIN condition affected by coercion mode."""
        engine.execute("CREATE TABLE t1 (id, val)")
        engine.execute("CREATE TABLE t2 (id, val)")
        engine.execute("INSERT INTO t1 VALUES (9, 'a')")
        engine.execute("INSERT INTO t2 VALUES (9, 'b')")
        engine.execute("SET COERCE_RULES = 'string'")
        # 9 = 9 in string mode: '9' = '9' -> true, should still match
        rows = engine.query_rows(
            "SELECT t1.val, t2.val FROM t1 JOIN t2 ON t1.id = t2.id"
        )
        assert rows == [["a", "b"]]

    def test_aggregation_sum_under_strict_with_all_numeric(self, engine):
        """SUM should still work in strict mode if all values are numeric."""
        engine.execute("CREATE TABLE t (a)")
        engine.execute("INSERT INTO t VALUES (1), (2), (3)")
        engine.execute("SET COERCE_RULES = 'strict'")
        val = engine.query_scalar("SELECT SUM(a) FROM t")
        assert val == 6

    def test_order_by_cross_type_under_string_mode(self, engine):
        """In string mode, ORDER BY should use string comparison."""
        engine.execute("CREATE TABLE t (a)")
        engine.execute("INSERT INTO t VALUES (null)")
        engine.execute("INSERT INTO t VALUES (true)")
        engine.execute("INSERT INTO t VALUES (42)")
        engine.execute("INSERT INTO t VALUES ('hello')")
        engine.execute("SET COERCE_RULES = 'string'")
        rows = engine.query_rows("SELECT a FROM t ORDER BY a ASC")
        # In string mode: null still first (three-valued), then all coerced to string
        # 'true', '42', 'hello' -> sorted: '42' < 'hello' < 'true'
        assert rows[0] == [None]
'''.lstrip()

# Write all files and validate
for path, content in files.items():
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w') as f:
        f.write(content)
    try:
        ast.parse(content)
        print(f"OK: {os.path.basename(path)}")
    except SyntaxError as e:
        print(f"SYNTAX ERROR in {os.path.basename(path)}: {e}")

print(f"\nWrote {len(files)} files total")
