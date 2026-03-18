"""
Performance tests for Stage 2: Procedural Maze Generation & Textures.

Measures maze generation time, textured rendering frame time, and large maze generation.
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


class TestTexturedRenderFrameTime:
    """Measure rendering performance with textures."""

    def test_textured_render_frame_time(self, page):
        """Frame time with textures applied."""
        page.evaluate("() => window.game.regenerateMaze(15, 15)")
        page.wait_for_timeout(500)

        times = page.evaluate("""() => {
            return new Promise(resolve => {
                const results = [];
                let moves = 0;
                const keys = ['d', 'd', 'd', 'd', 'w', 'w', 'w', 'd', 'w', 'w'];

                function doMove() {
                    if (moves >= keys.length) {
                        resolve(results);
                        return;
                    }
                    const start = performance.now();
                    const event = new KeyboardEvent('keydown', {key: keys[moves]});
                    document.dispatchEvent(event);
                    requestAnimationFrame(() => {
                        const end = performance.now();
                        results.push(end - start);
                        moves++;
                        setTimeout(doMove, 50);
                    });
                }
                doMove();
            });
        }""")

        if times and len(times) > 0:
            avg_ms = sum(times) / len(times)
            max_ms = max(times)
            print(json.dumps({
                "bench_metric": "textured_render_frame_time_seconds",
                "test": "test_textured_render_frame_time",
                "value": round(avg_ms / 1000, 6),
                "duration_seconds": round(avg_ms / 1000, 6),
                "iterations": len(times),
            }))
