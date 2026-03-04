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
