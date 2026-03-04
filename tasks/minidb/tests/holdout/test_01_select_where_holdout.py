"""Stage 1 holdout tests: edge cases and cross-feature interactions."""
import pytest


class TestEdgeCases:
    def test_empty_table_select(self, engine):
        engine.execute("CREATE TABLE t (a, b)")
        cols, rows = engine.query("SELECT * FROM t")
        assert cols == ["a", "b"]
        assert rows == []

    def test_single_quote_escape_in_string(self, engine):
        """Strings with escaped quotes: 'it''s'"""
        engine.execute("CREATE TABLE t (a)")
        engine.execute("INSERT INTO t VALUES ('it''s')")
        rows = engine.query_rows("SELECT a FROM t")
        assert rows[0][0] == "it's"

    def test_negative_numbers(self, engine):
        engine.execute("CREATE TABLE t (a)")
        engine.execute("INSERT INTO t VALUES (-42)")
        engine.execute("INSERT INTO t VALUES (-3.14)")
        rows = engine.query_rows("SELECT a FROM t WHERE a < 0")
        assert len(rows) == 2

    def test_integer_division_truncation(self, engine):
        engine.execute("CREATE TABLE t (a, b)")
        engine.execute("INSERT INTO t VALUES (7, 2)")
        rows = engine.query_rows("SELECT a / b FROM t")
        assert rows[0][0] == 3  # integer truncation toward zero

    def test_int_float_division(self, engine):
        engine.execute("CREATE TABLE t (a, b)")
        engine.execute("INSERT INTO t VALUES (7, 2.0)")
        rows = engine.query_rows("SELECT a / b FROM t")
        assert rows[0][0] == 3.5  # float result

    def test_modulo(self, engine):
        engine.execute("CREATE TABLE t (a, b)")
        engine.execute("INSERT INTO t VALUES (7, 3)")
        rows = engine.query_rows("SELECT a % b FROM t")
        assert rows[0][0] == 1

    def test_nested_list_insert_and_retrieve(self, engine):
        engine.execute("CREATE TABLE t (a)")
        engine.execute("INSERT INTO t VALUES ([[1, 2], [3, 4]])")
        rows = engine.query_rows("SELECT a FROM t")
        assert rows[0][0] == [[1, 2], [3, 4]]

    def test_typeof_all_types(self, engine):
        engine.execute("CREATE TABLE t (a)")
        engine.execute("INSERT INTO t VALUES (1)")
        engine.execute("INSERT INTO t VALUES (1.5)")
        engine.execute("INSERT INTO t VALUES ('s')")
        engine.execute("INSERT INTO t VALUES (true)")
        engine.execute("INSERT INTO t VALUES (null)")
        engine.execute("INSERT INTO t VALUES ([1])")
        engine.execute("INSERT INTO t VALUES (x'ff' AS 'image/png')")
        engine.execute("INSERT INTO t VALUES (ts'2025-01-01T00:00:00Z')")
        rows = engine.query_rows("SELECT TYPEOF(a) FROM t")
        types = [r[0] for r in rows]
        assert types == ["integer", "float", "string", "boolean", "null", "list", "blob", "timestamp"]

    def test_sizeof_blob(self, engine):
        engine.execute("CREATE TABLE t (a)")
        engine.execute("INSERT INTO t VALUES (x'aabbccdd' AS 'application/octet-stream')")
        rows = engine.query_rows("SELECT SIZEOF(a) FROM t")
        assert rows[0][0] == 4  # 4 bytes

    def test_multiple_tables(self, engine):
        engine.execute("CREATE TABLE t1 (a)")
        engine.execute("CREATE TABLE t2 (b)")
        engine.execute("INSERT INTO t1 VALUES (1)")
        engine.execute("INSERT INTO t2 VALUES (2)")
        r1 = engine.query_rows("SELECT a FROM t1")
        r2 = engine.query_rows("SELECT b FROM t2")
        assert r1 == [[1]]
        assert r2 == [[2]]


class TestCoercionEdgeCases:
    def test_string_that_looks_like_float(self, engine):
        engine.execute("CREATE TABLE t (a)")
        engine.execute("INSERT INTO t VALUES ('3.14')")
        rows = engine.query_rows("SELECT a FROM t WHERE a > 3")
        assert rows == [["3.14"]]

    def test_string_not_a_number_comparison(self, engine):
        """Non-numeric string compared to number -> false (not error)."""
        engine.execute("CREATE TABLE t (a)")
        engine.execute("INSERT INTO t VALUES ('abc')")
        rows = engine.query_rows("SELECT a FROM t WHERE a > 0")
        assert rows == []

    def test_null_in_arithmetic(self, engine):
        engine.execute("CREATE TABLE t (a)")
        engine.execute("INSERT INTO t VALUES (null)")
        resp = engine.execute("SELECT a + 1 FROM t")
        # null + 1: null propagation in arithmetic
        assert resp["rows"][0][0] is None

    def test_bool_string_comparison(self, engine):
        """Boolean compared to string: cross-type -> false."""
        engine.execute("CREATE TABLE t (a)")
        engine.execute("INSERT INTO t VALUES (true)")
        rows = engine.query_rows("SELECT a FROM t WHERE a = 'true'")
        # bool vs string is cross-type -> false
        assert rows == []

    def test_int_float_equality(self, engine):
        engine.execute("CREATE TABLE t (a)")
        engine.execute("INSERT INTO t VALUES (1)")
        rows = engine.query_rows("SELECT a FROM t WHERE a = 1.0")
        assert rows == [[1]]

    def test_not_operator(self, engine):
        engine.execute("CREATE TABLE t (a)")
        engine.execute("INSERT INTO t VALUES (1)")
        engine.execute("INSERT INTO t VALUES (2)")
        engine.execute("INSERT INTO t VALUES (3)")
        rows = engine.query_rows("SELECT a FROM t WHERE NOT a = 2")
        vals = [r[0] for r in rows]
        assert sorted(vals) == [1, 3]

    def test_complex_expression_in_select(self, engine):
        engine.execute("CREATE TABLE t (a, b)")
        engine.execute("INSERT INTO t VALUES (10, 3)")
        rows = engine.query_rows("SELECT a * 2 + b FROM t")
        assert rows[0][0] == 23

    def test_where_on_expression(self, engine):
        engine.execute("CREATE TABLE t (a, b)")
        engine.execute("INSERT INTO t VALUES (10, 3)")
        engine.execute("INSERT INTO t VALUES (1, 3)")
        rows = engine.query_rows("SELECT a FROM t WHERE a * b > 20")
        assert rows == [[10]]

    def test_no_such_column(self, engine):
        engine.execute("CREATE TABLE t (a)")
        engine.expect_error("SELECT nonexistent FROM t", "No such column")

    def test_or_with_null(self, engine):
        """true OR null -> true; false OR null -> null (excluded from WHERE)."""
        engine.execute("CREATE TABLE t (a, b)")
        engine.execute("INSERT INTO t VALUES (1, null)")
        # 1 > 0 is true; null > 0 is null. true OR null -> true
        rows = engine.query_rows("SELECT a FROM t WHERE a > 0 OR b > 0")
        assert rows == [[1]]

    def test_and_with_null(self, engine):
        """true AND null -> null (excluded from WHERE)."""
        engine.execute("CREATE TABLE t (a, b)")
        engine.execute("INSERT INTO t VALUES (1, null)")
        rows = engine.query_rows("SELECT a FROM t WHERE a > 0 AND b > 0")
        assert rows == []

    def test_case_insensitive_keywords(self, engine):
        engine.execute("create table T (A)")
        engine.execute("insert into T values (1)")
        rows = engine.query_rows("select A from T where A = 1")
        assert rows == [[1]]
