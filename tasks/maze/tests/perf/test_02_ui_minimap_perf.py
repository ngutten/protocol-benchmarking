"""
Performance tests for Stage 2: First-Person Rendering & Minimap.

Measures rendering frame time during movement.
"""
import json
import time
import pytest
from ..conftest import (
    get_player_position, get_player_direction, press_game_key,
    get_element_dimensions, get_maze_cell,
)


class TestRenderFrameTime:
    """Measure rendering performance."""

    def test_render_frame_time(self, page):
        """Measure time for canvas updates during movement."""
        # Find an open direction
        pos = get_player_position(page)
        deltas = {"N": (0, -1), "E": (1, 0), "S": (0, 1), "W": (-1, 0)}
        for _ in range(4):
            d = get_player_direction(page)
            dx, dy = deltas[d]
            cell = get_maze_cell(page, pos[0] + dx, pos[1] + dy)
            if cell not in ("#", "~"):
                break
            press_game_key(page, "d", wait_ms=50)

        # Measure frame times over multiple moves/turns
        times = page.evaluate("""() => {
            return new Promise(resolve => {
                const results = [];
                let moves = 0;
                const keys = ['d', 'd', 'd', 'd', 'w', 'w', 'w'];

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
                "bench_metric": "render_frame_time_seconds",
                "test": "test_render_frame_time",
                "value": round(avg_ms / 1000, 6),
                "duration_seconds": round(avg_ms / 1000, 6),
                "iterations": len(times),
            }))
