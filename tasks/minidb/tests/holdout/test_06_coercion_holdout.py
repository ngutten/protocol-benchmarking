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
