"""Performance benchmarks for Stage 3: Turn System, Enemies, AI."""
import time


class TestEnemyPhaseThroughput:
    """Measure enemy-turn processing with varying numbers of enemies."""

    def _spawn_enemies(self, game, count):
        """Spawn enemies scattered around the map."""
        s = game.state()
        w = s["map"]["width"]
        h = s["map"]["height"]
        spawned = 0
        for i in range(count):
            x = 2 + (i * 3) % (w - 4)
            y = 2 + (i * 5) % (h - 4)
            eid = game.spawn_creature("goblin", x, y)
            if eid is not None:
                spawned += 1
        return spawned

    def test_enemy_phase_5_enemies(self, game):
        """Force 100 enemy phases with 5 enemies on the map."""
        self._spawn_enemies(game, 5)
        start = time.perf_counter()
        for _ in range(100):
            game.force_enemy_phase()
        elapsed = time.perf_counter() - start
        print(f'{{"bench_metric": "ops_per_second", "test": "test_enemy_phase_5_enemies", '
              f'"value": {100 / elapsed:.2f}, "iterations": 100, "enemies": 5, '
              f'"duration_seconds": {elapsed:.6f}}}')

    def test_enemy_phase_20_enemies(self, game):
        """Force 50 enemy phases with 20 enemies on the map."""
        self._spawn_enemies(game, 20)
        start = time.perf_counter()
        for _ in range(50):
            game.force_enemy_phase()
        elapsed = time.perf_counter() - start
        print(f'{{"bench_metric": "ops_per_second", "test": "test_enemy_phase_20_enemies", '
              f'"value": {50 / elapsed:.2f}, "iterations": 50, "enemies": 20, '
              f'"duration_seconds": {elapsed:.6f}}}')


class TestMoveWithEnemyPhase:
    """Measure full turn cycles (player move triggers enemy phase)."""

    def test_full_turn_cycle_100(self, game):
        """100 full turn cycles: move until bar empties, enemies act."""
        s = game.state()
        w = s["map"]["width"]
        h = s["map"]["height"]
        for i in range(5):
            game.spawn_creature("goblin", 2 + i * 3, 2)
        directions = ["MoveE", "MoveW"]
        start = time.perf_counter()
        for i in range(100):
            game.execute(directions[i % 2])
        elapsed = time.perf_counter() - start
        print(f'{{"bench_metric": "ops_per_second", "test": "test_full_turn_cycle_100", '
              f'"value": {100 / elapsed:.2f}, "iterations": 100, '
              f'"duration_seconds": {elapsed:.6f}}}')
