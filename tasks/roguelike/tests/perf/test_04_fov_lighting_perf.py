"""Performance benchmarks for Stage 4: FOV & Lighting."""
import time


class TestFOVComputationThroughput:
    """Measure FOV recomputation cost after movement."""

    def test_fov_complex_map_movement_200(self, game):
        """200 moves on a map with interior walls that create complex FOV geometry."""
        s = game.state()
        w = s["map"]["width"]
        h = s["map"]["height"]
        for col in range(4, w - 4, 4):
            gap = (col * 3) % (h - 6) + 3
            for row in range(2, h - 2):
                if row != gap:
                    game.set_tile(col, row, "wall")
        game.move_to(3, h // 2)
        directions = ["MoveE", "MoveW"]
        start = time.perf_counter()
        for i in range(200):
            game.execute(directions[i % 2])
            game.state()
        elapsed = time.perf_counter() - start
        print(f'{{"bench_metric": "ops_per_second", "test": "test_fov_complex_map_movement_200", '
              f'"value": {200 / elapsed:.2f}, "iterations": 200, '
              f'"duration_seconds": {elapsed:.6f}}}')

    def test_fov_after_movement_200(self, game):
        """200 moves that each trigger FOV recomputation."""
        directions = ["MoveE", "MoveW"]
        start = time.perf_counter()
        for i in range(200):
            game.execute(directions[i % 2])
            game.state()
        elapsed = time.perf_counter() - start
        print(f'{{"bench_metric": "ops_per_second", "test": "test_fov_after_movement_200", '
              f'"value": {200 / elapsed:.2f}, "iterations": 200, '
              f'"duration_seconds": {elapsed:.6f}}}')


class TestFOVWithEnemies:
    """FOV computation with enemies that also compute FOV each turn."""

    def test_fov_with_10_enemies(self, game):
        """50 enemy phases where each enemy also computes FOV for detection."""
        s = game.state()
        w = s["map"]["width"]
        h = s["map"]["height"]
        for i in range(10):
            x = 2 + (i * 3) % (w - 4)
            y = 2 + (i * 5) % (h - 4)
            game.spawn_creature("goblin", x, y)
        start = time.perf_counter()
        for _ in range(50):
            game.force_enemy_phase()
        elapsed = time.perf_counter() - start
        print(f'{{"bench_metric": "ops_per_second", "test": "test_fov_with_10_enemies", '
              f'"value": {50 / elapsed:.2f}, "iterations": 50, "enemies": 10, '
              f'"duration_seconds": {elapsed:.6f}}}')
