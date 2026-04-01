"""Performance benchmarks for Stage 8: Ranged & Targeting."""
import time


class TestTargetingModeThroughput:
    """Measure targeting mode entry/exit which computes valid targets and LOS."""

    def test_targeting_enter_exit_100(self, game):
        """Enter and exit targeting mode 100 times with 15 enemies on map."""
        resp = game.create_item("shortbow")
        item_id = resp.get("item_id")
        if item_id is not None:
            game.force_equip(item_id)
        s = game.state()
        w = s["map"]["width"]
        h = s["map"]["height"]
        for i in range(15):
            x = 2 + (i * 3) % (w - 4)
            y = 2 + (i * 5) % (h - 4)
            game.spawn_creature("goblin", x, y)
        start = time.perf_counter()
        for _ in range(100):
            game.execute("Fire")
            game.execute("Cancel")
        elapsed = time.perf_counter() - start
        print(f'{{"bench_metric": "ops_per_second", "test": "test_targeting_enter_exit_100", '
              f'"value": {100 / elapsed:.2f}, "iterations": 100, "enemies": 15, '
              f'"duration_seconds": {elapsed:.6f}}}')


class TestRangedCombatThroughput:
    """Measure ranged combat resolution speed."""

    def test_fire_action_50(self, game):
        """Equip a bow, spawn a target, and fire 50 times."""
        resp = game.create_item("shortbow")
        item_id = resp.get("item_id")
        if item_id is not None:
            game.force_equip(item_id)
        s = game.state()
        px, py = s["player_pos"]["x"], s["player_pos"]["y"]
        eid = game.spawn_creature("skeleton", px + 4, py)
        if eid is not None:
            game.set_hp(eid, 99999)
        start = time.perf_counter()
        for _ in range(50):
            game.execute("Fire")
            game.execute("Confirm")
        elapsed = time.perf_counter() - start
        print(f'{{"bench_metric": "ops_per_second", "test": "test_fire_action_50", '
              f'"value": {50 / elapsed:.2f}, "iterations": 50, '
              f'"duration_seconds": {elapsed:.6f}}}')
