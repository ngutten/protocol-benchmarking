"""Performance benchmarks for Stage 9: Procedural Generation."""
import time


class TestLevelGenerationThroughput:
    """Measure dungeon level generation speed."""

    def test_generate_10_levels(self, game):
        """Generate 10 dungeon levels sequentially."""
        start = time.perf_counter()
        for depth in range(1, 11):
            game.set_level(depth)
        elapsed = time.perf_counter() - start
        print(f'{{"bench_metric": "level_gen_time_seconds", "test": "test_generate_10_levels", '
              f'"value": {elapsed:.6f}, "iterations": 10, '
              f'"duration_seconds": {elapsed:.6f}}}')

    def test_generate_level_and_query_state(self, game):
        """Generate a level then query its full state (map + entities)."""
        start = time.perf_counter()
        for depth in range(1, 6):
            game.set_level(depth)
            game.state()
        elapsed = time.perf_counter() - start
        print(f'{{"bench_metric": "ops_per_second", "test": "test_generate_level_and_query_state", '
              f'"value": {5 / elapsed:.2f}, "iterations": 5, '
              f'"duration_seconds": {elapsed:.6f}}}')


class TestLevelTraversalThroughput:
    """Measure speed of revisiting already-generated levels."""

    def test_revisit_5_levels_20_times(self, game):
        """Generate 5 levels, then cycle through them 20 times."""
        for depth in range(1, 6):
            game.set_level(depth)
        start = time.perf_counter()
        for i in range(20):
            game.set_level((i % 5) + 1)
        elapsed = time.perf_counter() - start
        print(f'{{"bench_metric": "ops_per_second", "test": "test_revisit_5_levels_20_times", '
              f'"value": {20 / elapsed:.2f}, "iterations": 20, '
              f'"duration_seconds": {elapsed:.6f}}}')
