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
