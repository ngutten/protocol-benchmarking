"""
Performance tests for Stage 4: Texture Mapping.

Measures rendering performance with textures applied.
"""
import json
import time
import pytest
from ..conftest import (
    get_player_position, get_player_direction, press_game_key,
    get_element_dimensions, get_maze_cell,
)


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
