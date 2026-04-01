"""Performance benchmarks for Stage 1: Core Skeleton."""
import time


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
