"""
Performance tests for Stage 1: Dungeon Logic.

Measures movement response time and page load time.
"""
import json
import time
import pytest
from ..conftest import (
    get_player_position, get_player_direction, press_game_key,
    get_element_dimensions, get_maze_cell,
)


class TestMovementResponseTime:
    """Measure keypress-to-state-update latency."""

    def test_movement_response_time(self, page):
        """Measure keypress to game state update latency."""
        pos = get_player_position(page)
        deltas = {"N": (0, -1), "E": (1, 0), "S": (0, 1), "W": (-1, 0)}

        # Find an open direction
        for _ in range(4):
            d = get_player_direction(page)
            dx, dy = deltas[d]
            cell = get_maze_cell(page, pos[0] + dx, pos[1] + dy)
            if cell not in ("#", "~"):
                break
            press_game_key(page, "d", wait_ms=50)

        # Measure turn response times (always works regardless of walls)
        times = []
        for _ in range(10):
            start = time.perf_counter()
            page.keyboard.press("a")
            # Poll for direction change
            page.evaluate("() => window.game.getPlayerDirection()")
            end = time.perf_counter()
            times.append((end - start) * 1000)

        avg_ms = sum(times) / len(times)
        max_ms = max(times)
        print(json.dumps({
            "bench_metric": "movement_response_time_seconds",
            "test": "test_movement_response_time",
            "value": round(avg_ms / 1000, 6),
            "duration_seconds": round(avg_ms / 1000, 6),
            "iterations": len(times),
        }))


class TestPageLoadTime:
    """Measure page load performance."""

    def test_page_load_time(self, browser, base_url):
        """Measure time from navigation to game ready."""
        times = []
        for _ in range(3):
            pg = browser.new_page()
            start = time.perf_counter()
            pg.goto(f"{base_url}/index.html", wait_until="networkidle")
            pg.wait_for_function("typeof window.game !== 'undefined'", timeout=10000)
            end = time.perf_counter()
            times.append((end - start) * 1000)
            pg.close()

        avg_ms = sum(times) / len(times)
        print(json.dumps({
            "bench_metric": "page_load_time_seconds",
            "test": "test_page_load_time",
            "value": round(avg_ms / 1000, 6),
            "duration_seconds": round(avg_ms / 1000, 6),
            "iterations": len(times),
        }))
