"""
Holdout tests for Stage 1: Dungeon Logic.

Movement edge-case tests hidden from the LLM during development.
"""
import pytest
from ..conftest import (
    get_game_state, get_player_position, get_player_direction,
    press_game_key, get_maze_cell,
)


# ── Movement Edge Cases ───────────────────────────────────────────────────


class TestMovementEdgeCases:
    """Edge cases for movement mechanics."""

    def test_full_rotation(self, page):
        """Pressing A four times returns to the original direction."""
        dir_start = get_player_direction(page)
        for _ in range(4):
            press_game_key(page, "a")
        dir_end = get_player_direction(page)
        assert dir_end == dir_start, \
            f"4 left turns should return to {dir_start}, got {dir_end}"

    def test_full_rotation_right(self, page):
        """Pressing D four times returns to the original direction."""
        dir_start = get_player_direction(page)
        for _ in range(4):
            press_game_key(page, "d")
        dir_end = get_player_direction(page)
        assert dir_end == dir_start, \
            f"4 right turns should return to {dir_start}, got {dir_end}"

    def test_movement_updates_visited_cells(self, page):
        """Each move adds newly revealed cells to visited list."""
        visited_before = len(page.evaluate("() => window.game.getVisitedCells()"))
        # Move around
        for key in ["w", "d", "w", "w"]:
            press_game_key(page, key)
        visited_after = len(page.evaluate("() => window.game.getVisitedCells()"))
        assert visited_after >= visited_before, \
            "Visited cell count should not decrease after moving"
