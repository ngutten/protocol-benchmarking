"""
Performance tests for Stage 3: Procedural Maze Generation.

Measures maze generation time for standard and large mazes.
"""
import json
import time
import pytest
from ..conftest import (
    get_player_position, get_player_direction, press_game_key,
    get_element_dimensions, get_maze_cell,
)


class TestMazeGenerationTime:
    """Measure maze generation performance."""

    def test_maze_generation_time(self, page):
        """Measure regenerateMaze() execution time."""
        times = []
        for _ in range(5):
            elapsed = page.evaluate("""() => {
                const start = performance.now();
                window.game.regenerateMaze(15, 15);
                const end = performance.now();
                return end - start;
            }""")
            times.append(elapsed)

        avg_ms = sum(times) / len(times)
        print(json.dumps({
            "bench_metric": "maze_generation_time_seconds",
            "test": "test_maze_generation_time",
            "value": round(avg_ms / 1000, 6),
            "duration_seconds": round(avg_ms / 1000, 6),
            "iterations": len(times),
        }))

    def test_large_maze_generation(self, page):
        """Generate a large maze (50x50+) and measure time."""
        elapsed = page.evaluate("""() => {
            const start = performance.now();
            window.game.regenerateMaze(50, 50);
            const end = performance.now();
            return end - start;
        }""")

        print(json.dumps({
            "bench_metric": "large_maze_generation_time_seconds",
            "test": "test_large_maze_generation",
            "value": round(elapsed / 1000, 6),
            "duration_seconds": round(elapsed / 1000, 6),
            "iterations": 1,
        }))
