"""Performance benchmarks for Stage 2: Stats & Modifiers."""
import time


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
