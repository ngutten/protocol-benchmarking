"""Performance benchmarks for Stage 11: Save / Load."""
import time


class TestSaveLoadThroughput:
    """Measure save and load cycle time."""

    def _build_complex_state(self, game):
        """Set up a non-trivial game state for save/load benchmarking."""
        for template in ["iron_sword", "iron_helmet", "leather_armor",
                         "speed_boots", "ring_of_light"]:
            resp = game.create_item(template)
            item_id = resp.get("item_id")
            if item_id is not None:
                game.force_equip(item_id)
        for _ in range(20):
            game.create_item("healing_potion")
        for ab in ["leaping_strike", "magic_missile", "sleep"]:
            game.learn_ability(ab)
        s = game.state()
        w = s["map"]["width"]
        h = s["map"]["height"]
        for i in range(8):
            x = 2 + (i * 3) % (w - 4)
            y = 2 + (i * 5) % (h - 4)
            game.spawn_creature("goblin", x, y)

    def test_save_10_times(self, game):
        """Save game state 10 times with a loaded game."""
        self._build_complex_state(game)
        start = time.perf_counter()
        for _ in range(10):
            game.save_game()
        elapsed = time.perf_counter() - start
        print(f'{{"bench_metric": "ops_per_second", "test": "test_save_10_times", '
              f'"value": {10 / elapsed:.2f}, "iterations": 10, '
              f'"duration_seconds": {elapsed:.6f}}}')

    def test_save_load_cycle_10(self, game):
        """Save then load 10 times."""
        self._build_complex_state(game)
        resp = game.save_game()
        path = resp.get("path", "")
        if not path:
            return
        start = time.perf_counter()
        for _ in range(10):
            game.save_game(path)
            game.load_game(path)
        elapsed = time.perf_counter() - start
        print(f'{{"bench_metric": "ops_per_second", "test": "test_save_load_cycle_10", '
              f'"value": {10 / elapsed:.2f}, "iterations": 10, '
              f'"duration_seconds": {elapsed:.6f}}}')


class TestSaveWithMultipleLevels:
    """Measure save/load time with multiple generated levels."""

    def test_save_load_with_5_levels(self, game):
        """Generate 5 levels, save/load 5 times."""
        for depth in range(1, 6):
            game.set_level(depth)
        resp = game.save_game()
        path = resp.get("path", "")
        if not path:
            return
        start = time.perf_counter()
        for _ in range(5):
            game.save_game(path)
            game.load_game(path)
        elapsed = time.perf_counter() - start
        print(f'{{"bench_metric": "ops_per_second", "test": "test_save_load_with_5_levels", '
              f'"value": {5 / elapsed:.2f}, "iterations": 5, "levels": 5, '
              f'"duration_seconds": {elapsed:.6f}}}')
