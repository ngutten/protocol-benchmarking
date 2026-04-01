"""Performance benchmarks for Stage 1: Core Skeleton, Stats & Modifiers, Turn System & Enemies."""
import time


# ---------------------------------------------------------------------------
# Core Skeleton
# ---------------------------------------------------------------------------

class TestMovementThroughput:
    """Measure how fast the engine processes movement commands."""

    def test_movement_200_steps(self, game):
        """200 movement commands (alternating east/west)."""
        actions = ["MoveE", "MoveW"] * 100
        start = time.perf_counter()
        for action in actions:
            game.execute(action)
        elapsed = time.perf_counter() - start
        print(f'{{"bench_metric": "ops_per_second", "test": "test_movement_200_steps", '
              f'"value": {200 / elapsed:.2f}, "iterations": 200, '
              f'"duration_seconds": {elapsed:.6f}}}')

    def test_movement_1000_steps(self, game):
        """1000 movement commands in cardinal directions."""
        directions = ["MoveN", "MoveE", "MoveS", "MoveW"]
        start = time.perf_counter()
        for i in range(1000):
            game.execute(directions[i % 4])
        elapsed = time.perf_counter() - start
        print(f'{{"bench_metric": "ops_per_second", "test": "test_movement_1000_steps", '
              f'"value": {1000 / elapsed:.2f}, "iterations": 1000, '
              f'"duration_seconds": {elapsed:.6f}}}')


class TestStateQueryThroughput:
    """Measure state snapshot speed."""

    def test_state_query_500(self, game):
        """500 state queries."""
        start = time.perf_counter()
        for _ in range(500):
            game.state()
        elapsed = time.perf_counter() - start
        print(f'{{"bench_metric": "ops_per_second", "test": "test_state_query_500", '
              f'"value": {500 / elapsed:.2f}, "iterations": 500, '
              f'"duration_seconds": {elapsed:.6f}}}')

    def test_interleaved_move_and_state(self, game):
        """200 move+state pairs (typical game loop pattern)."""
        directions = ["MoveE", "MoveW"]
        start = time.perf_counter()
        for i in range(200):
            game.execute(directions[i % 2])
            game.state()
        elapsed = time.perf_counter() - start
        print(f'{{"bench_metric": "ops_per_second", "test": "test_interleaved_move_and_state", '
              f'"value": {200 / elapsed:.2f}, "iterations": 200, '
              f'"duration_seconds": {elapsed:.6f}}}')


# ---------------------------------------------------------------------------
# Stats & Modifiers
# ---------------------------------------------------------------------------

class TestModifierStackThroughput:
    """Measure modifier stack and derived stat recalculation speed."""

    def test_levelup_and_move_100(self, game):
        """Level up 20 times with movement between each, exercising modifier stack."""
        directions = ["MoveE", "MoveW"]
        start = time.perf_counter()
        for i in range(20):
            game.set_xp((i + 1) * 500)
            for j in range(5):
                game.execute(directions[j % 2])
            game.state()
        elapsed = time.perf_counter() - start
        print(f'{{"bench_metric": "ops_per_second", "test": "test_levelup_and_move_100", '
              f'"value": {100 / elapsed:.2f}, "iterations": 100, '
              f'"duration_seconds": {elapsed:.6f}}}')


class TestLevelUpThroughput:
    """Measure XP award and level-up processing speed."""

    def test_rapid_level_ups(self, game):
        """Grant XP to trigger 50 level-ups and query state each time."""
        start = time.perf_counter()
        for i in range(50):
            game.set_xp((i + 1) * 500)
            game.state()
        elapsed = time.perf_counter() - start
        print(f'{{"bench_metric": "ops_per_second", "test": "test_rapid_level_ups", '
              f'"value": {50 / elapsed:.2f}, "iterations": 50, '
              f'"duration_seconds": {elapsed:.6f}}}')


# ---------------------------------------------------------------------------
# Turn System & Enemies
# ---------------------------------------------------------------------------

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
