"""Stage 1 training tests: Basic SELECT/WHERE with dynamic typing."""
import pytest


class TestCreateAndInsert:
    def test_create_table(self, engine):
        resp = engine.execute("CREATE TABLE t (a, b, c)")
        assert resp["ok"] is True

    def test_insert_and_select(self, engine):
        engine.execute("CREATE TABLE t (x, y)")
        engine.execute("INSERT INTO t VALUES (1, 'hello')")
        cols, rows = engine.query("SELECT x, y FROM t")
        assert cols == ["x", "y"]
        assert rows == [[1, "hello"]]

    def test_multi_row_insert(self, engine):
        engine.execute("CREATE TABLE t (a)")
        engine.execute("INSERT INTO t VALUES (1), (2), (3)")
        rows = engine.query_rows("SELECT a FROM t")
        assert len(rows) == 3

    def test_select_star(self, engine):
        engine.execute("CREATE TABLE t (a, b)")
        engine.execute("INSERT INTO t VALUES (1, 2)")
        cols, rows = engine.query("SELECT * FROM t")
        assert cols == ["a", "b"]
        assert rows == [[1, 2]]

    def test_column_count_mismatch(self, engine):
        engine.execute("CREATE TABLE t (a, b)")
        engine.expect_error("INSERT INTO t VALUES (1, 2, 3)", "Expected")

    def test_drop_table(self, engine):
        engine.execute("CREATE TABLE t (a)")
        engine.execute("DROP TABLE t")
        engine.expect_error("SELECT * FROM t", "No such table")

    def test_no_such_table(self, engine):
        engine.expect_error("SELECT * FROM nonexistent", "No such table")


class TestDynamicTypes:
    def test_all_literal_types(self, engine):
        engine.execute("CREATE TABLE t (a)")
        engine.execute("INSERT INTO t VALUES (42)")
        engine.execute("INSERT INTO t VALUES (3.14)")
        engine.execute("INSERT INTO t VALUES ('hello')")
        engine.execute("INSERT INTO t VALUES (true)")
        engine.execute("INSERT INTO t VALUES (false)")
        engine.execute("INSERT INTO t VALUES (null)")
        rows = engine.query_rows("SELECT a FROM t")
        assert len(rows) == 6
        assert rows[0] == [42]
        assert rows[1] == [3.14]
        assert rows[2] == ["hello"]
        assert rows[3] == [True]
        assert rows[4] == [False]
        assert rows[5] == [None]

    def test_blob_insert(self, engine):
        engine.execute("CREATE TABLE t (id, data)")
        engine.execute("INSERT INTO t VALUES (1, x'deadbeef' AS 'application/octet-stream')")
        rows = engine.query_rows("SELECT data FROM t")
        blob = rows[0][0]
        assert blob["__blob__"] is True
        assert blob["mime"] == "application/octet-stream"
        assert blob["size"] == 4

    def test_list_insert(self, engine):
        engine.execute("CREATE TABLE t (id, tags)")
        engine.execute("INSERT INTO t VALUES (1, [1, 'a', true, null])")
        rows = engine.query_rows("SELECT tags FROM t")
        assert rows[0][0] == [1, "a", True, None]

    def test_timestamp_insert(self, engine):
        engine.execute("CREATE TABLE t (id, ts)")
        engine.execute("INSERT INTO t VALUES (1, ts'2025-03-15T10:30:00Z')")
        rows = engine.query_rows("SELECT ts FROM t")
        assert rows[0][0]["__ts__"] == "2025-03-15T10:30:00Z"

    def test_typeof(self, engine):
        engine.execute("CREATE TABLE t (a)")
        engine.execute("INSERT INTO t VALUES (42)")
        engine.execute("INSERT INTO t VALUES ('hi')")
        engine.execute("INSERT INTO t VALUES (true)")
        engine.execute("INSERT INTO t VALUES (null)")
        rows = engine.query_rows("SELECT TYPEOF(a) FROM t")
        assert rows[0][0] == "integer"
        assert rows[1][0] == "string"
        assert rows[2][0] == "boolean"
        assert rows[3][0] == "null"

    def test_sizeof(self, engine):
        engine.execute("CREATE TABLE t (a)")
        engine.execute("INSERT INTO t VALUES ('hello')")
        engine.execute("INSERT INTO t VALUES ([1, 2, 3])")
        engine.execute("INSERT INTO t VALUES (42)")
        rows = engine.query_rows("SELECT SIZEOF(a) FROM t")
        assert rows[0][0] == 5    # string length
        assert rows[1][0] == 3    # list length
        assert rows[2][0] is None  # not applicable


class TestWhereAndCoercion:
    def test_simple_where(self, engine):
        engine.execute("CREATE TABLE t (a, b)")
        engine.execute("INSERT INTO t VALUES (1, 'x'), (2, 'y'), (3, 'z')")
        rows = engine.query_rows("SELECT a FROM t WHERE a > 1")
        vals = [r[0] for r in rows]
        assert sorted(vals) == [2, 3]

    def test_string_numeric_coercion_in_comparison(self, engine):
        engine.execute("CREATE TABLE t (a)")
        engine.execute("INSERT INTO t VALUES ('10')")
        engine.execute("INSERT INTO t VALUES ('abc')")
        engine.execute("INSERT INTO t VALUES (5)")
        rows = engine.query_rows("SELECT a FROM t WHERE a > 7")
        # '10' coerces to 10 > 7 = true; 'abc' fails coercion = false; 5 > 7 = false
        assert rows == [["10"]]

    def test_boolean_numeric_coercion(self, engine):
        engine.execute("CREATE TABLE t (a)")
        engine.execute("INSERT INTO t VALUES (true)")
        engine.execute("INSERT INTO t VALUES (false)")
        rows = engine.query_rows("SELECT a + 10 FROM t")
        assert rows[0][0] == 11
        assert rows[1][0] == 10

    def test_null_comparison_three_valued(self, engine):
        engine.execute("CREATE TABLE t (a)")
        engine.execute("INSERT INTO t VALUES (1)")
        engine.execute("INSERT INTO t VALUES (null)")
        engine.execute("INSERT INTO t VALUES (3)")
        # WHERE a > 0: null > 0 yields null, which is falsy in WHERE
        rows = engine.query_rows("SELECT a FROM t WHERE a > 0")
        vals = [r[0] for r in rows]
        assert sorted(vals) == [1, 3]

    def test_is_null(self, engine):
        engine.execute("CREATE TABLE t (a)")
        engine.execute("INSERT INTO t VALUES (1)")
        engine.execute("INSERT INTO t VALUES (null)")
        rows = engine.query_rows("SELECT a FROM t WHERE a IS NULL")
        assert rows == [[None]]

    def test_is_not_null(self, engine):
        engine.execute("CREATE TABLE t (a)")
        engine.execute("INSERT INTO t VALUES (1)")
        engine.execute("INSERT INTO t VALUES (null)")
        rows = engine.query_rows("SELECT a FROM t WHERE a IS NOT NULL")
        assert rows == [[1]]

    def test_cross_type_comparison_false(self, engine):
        """Comparing a blob to an integer should yield false, not error."""
        engine.execute("CREATE TABLE t (a)")
        engine.execute("INSERT INTO t VALUES (x'ff' AS 'image/png')")
        engine.execute("INSERT INTO t VALUES (42)")
        rows = engine.query_rows("SELECT a FROM t WHERE a = 42")
        assert len(rows) == 1
        assert rows[0][0] == 42

    def test_string_concatenation(self, engine):
        engine.execute("CREATE TABLE t (a, b)")
        engine.execute("INSERT INTO t VALUES ('hello', ' world')")
        rows = engine.query_rows("SELECT a + b FROM t")
        assert rows[0][0] == "hello world"

    def test_string_numeric_concat(self, engine):
        engine.execute("CREATE TABLE t (a, b)")
        engine.execute("INSERT INTO t VALUES ('count: ', 42)")
        rows = engine.query_rows("SELECT a + b FROM t")
        assert rows[0][0] == "count: 42"

    def test_arithmetic_error_per_row(self, engine):
        """Arithmetic type errors produce null + warning, not query failure."""
        engine.execute("CREATE TABLE t (a, b)")
        engine.execute("INSERT INTO t VALUES (1, 2)")
        engine.execute("INSERT INTO t VALUES (1, true)")  # bool coerces to number
        engine.execute("INSERT INTO t VALUES (1, [1,2])")  # list + int = error
        resp = engine.execute("SELECT a + b FROM t")
        rows = resp["rows"]
        assert rows[0][0] == 3       # 1 + 2
        assert rows[1][0] == 2       # 1 + true(=1)
        assert rows[2][0] is None    # error -> null
        assert "warnings" in resp

    def test_logical_operators(self, engine):
        engine.execute("CREATE TABLE t (a, b)")
        engine.execute("INSERT INTO t VALUES (1, 10)")
        engine.execute("INSERT INTO t VALUES (2, 20)")
        engine.execute("INSERT INTO t VALUES (3, 5)")
        rows = engine.query_rows("SELECT a FROM t WHERE a > 1 AND b > 10")
        assert rows == [[2]]

    def test_aliased_columns(self, engine):
        engine.execute("CREATE TABLE t (a)")
        engine.execute("INSERT INTO t VALUES (1)")
        cols, rows = engine.query("SELECT a AS renamed FROM t")
        assert cols == ["renamed"]


class TestCast:
    def test_cast_string_to_int(self, engine):
        engine.execute("CREATE TABLE t (a)")
        engine.execute("INSERT INTO t VALUES ('42')")
        rows = engine.query_rows("SELECT CAST(a AS 'integer') FROM t")
        assert rows[0][0] == 42

    def test_cast_impossible(self, engine):
        """CAST of impossible conversion should produce per-row error."""
        engine.execute("CREATE TABLE t (a)")
        engine.execute("INSERT INTO t VALUES ('not_a_number')")
        resp = engine.execute("SELECT CAST(a AS 'integer') FROM t")
        assert resp["rows"][0][0] is None
        assert "warnings" in resp
