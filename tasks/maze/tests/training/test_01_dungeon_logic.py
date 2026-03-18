"""
Training tests for Stage 1: Dungeon Logic.

Tests focus on maze loading, movement mechanics, terrain collision rules,
goal detection, and the JavaScript API — not on visual rendering.
"""
import pytest
from ..conftest import (
    get_game_state, get_player_position, get_player_direction,
    press_game_key, get_element_dimensions,
    get_maze_cell, find_cell_of_type,
    find_adjacent_open_cell, navigate_to_cell, face_direction,
)


# ── Page & DOM ───────────────────────────────────────────────────────────


class TestPageAndDOM:
    """Verify the game page loads and required DOM elements exist."""

    def test_page_loads_with_game_view(self, page):
        """The #game-view element exists and has non-zero dimensions."""
        dims = get_element_dimensions(page, "#game-view")
        assert dims is not None, "#game-view element not found"
        assert dims["width"] > 0, "#game-view has zero width"
        assert dims["height"] > 0, "#game-view has zero height"

    def test_game_message_element_exists(self, page):
        """The #game-message element exists in the DOM."""
        el = page.query_selector("#game-message")
        assert el is not None, "#game-message element not found"


# ── Movement ──────────────────────────────────────────────────────────────


class TestMovement:
    """Verify WASD grid-based movement mechanics."""

    def test_api_returns_valid_position(self, page):
        """getPlayerPosition() returns an object with x and y integers."""
        pos = page.evaluate("() => window.game.getPlayerPosition()")
        assert isinstance(pos, dict), "getPlayerPosition() should return an object"
        assert "x" in pos and "y" in pos, "Position must have x and y"
        assert isinstance(pos["x"], int), "x must be an integer"
        assert isinstance(pos["y"], int), "y must be an integer"

    def test_api_returns_valid_direction(self, page):
        """getPlayerDirection() returns N, E, S, or W."""
        d = get_player_direction(page)
        assert d in ("N", "E", "S", "W"), f"Invalid direction: {d}"

    def test_w_moves_forward(self, page):
        """Pressing W moves the player one cell in the facing direction."""
        pos_before = get_player_position(page)
        direction = get_player_direction(page)
        deltas = {"N": (0, -1), "E": (1, 0), "S": (0, 1), "W": (-1, 0)}
        dx, dy = deltas[direction]
        expected_x, expected_y = pos_before[0] + dx, pos_before[1] + dy
        # Check if the target cell is traversable
        target_cell = get_maze_cell(page, expected_x, expected_y)
        if target_cell in ("#", "~"):
            # Turn to find an open direction first
            for _ in range(3):
                press_game_key(page, "d")
                direction = get_player_direction(page)
                dx, dy = deltas[direction]
                expected_x, expected_y = pos_before[0] + dx, pos_before[1] + dy
                target_cell = get_maze_cell(page, expected_x, expected_y)
                if target_cell not in ("#", "~"):
                    break
        if target_cell in ("#", "~"):
            pytest.skip("No open direction to move forward")
        press_game_key(page, "w")
        pos_after = get_player_position(page)
        assert pos_after == (expected_x, expected_y), \
            f"Expected move to ({expected_x}, {expected_y}), got {pos_after}"

    def test_s_moves_backward(self, page):
        """Pressing S moves the player one cell opposite to facing direction."""
        # First move forward to have room to go backward
        pos_start = get_player_position(page)
        direction = get_player_direction(page)
        deltas = {"N": (0, -1), "E": (1, 0), "S": (0, 1), "W": (-1, 0)}

        # Find an open direction and move forward
        for _ in range(4):
            d = get_player_direction(page)
            dx, dy = deltas[d]
            target = get_maze_cell(page, pos_start[0] + dx, pos_start[1] + dy)
            if target not in ("#", "~"):
                break
            press_game_key(page, "d")

        press_game_key(page, "w")
        pos_after_forward = get_player_position(page)
        if pos_after_forward == pos_start:
            pytest.skip("Could not move forward")

        # Now press S to move back
        press_game_key(page, "s")
        pos_after_back = get_player_position(page)
        assert pos_after_back == pos_start, \
            f"S should move back to {pos_start}, got {pos_after_back}"

    def test_a_turns_left(self, page):
        """Pressing A rotates direction 90 degrees left."""
        dir_before = get_player_direction(page)
        left_of = {"N": "W", "W": "S", "S": "E", "E": "N"}
        press_game_key(page, "a")
        dir_after = get_player_direction(page)
        assert dir_after == left_of[dir_before], \
            f"A from {dir_before} should give {left_of[dir_before]}, got {dir_after}"

    def test_d_turns_right(self, page):
        """Pressing D rotates direction 90 degrees right."""
        dir_before = get_player_direction(page)
        right_of = {"N": "E", "E": "S", "S": "W", "W": "N"}
        press_game_key(page, "d")
        dir_after = get_player_direction(page)
        assert dir_after == right_of[dir_before], \
            f"D from {dir_before} should give {right_of[dir_before]}, got {dir_after}"

    def test_wall_collision(self, page):
        """Moving into a wall does not change player position."""
        pos = get_player_position(page)
        direction = get_player_direction(page)
        deltas = {"N": (0, -1), "E": (1, 0), "S": (0, 1), "W": (-1, 0)}

        # Turn to face a wall
        for _ in range(4):
            d = get_player_direction(page)
            dx, dy = deltas[d]
            target = get_maze_cell(page, pos[0] + dx, pos[1] + dy)
            if target == "#":
                break
            press_game_key(page, "d")
        else:
            pytest.skip("No adjacent wall found from start position")

        pos_before = get_player_position(page)
        press_game_key(page, "w")
        pos_after = get_player_position(page)
        assert pos_after == pos_before, \
            f"Player should not move through wall: {pos_before} -> {pos_after}"


# ── Terrain ───────────────────────────────────────────────────────────────


class TestTerrain:
    """Verify terrain collision rules (movement-based, not visual)."""

    def test_water_blocks_movement(self, page):
        """Player cannot walk into a water (~) cell."""
        water = find_cell_of_type(page, "~")
        if water is None:
            pytest.skip("No water cells in maze")
        adj = find_adjacent_open_cell(page, water[0], water[1])
        if adj is None:
            pytest.skip("No accessible cell adjacent to water")
        # Navigate to the adjacent cell
        if not navigate_to_cell(page, adj[0], adj[1]):
            pytest.skip("Could not reach cell adjacent to water")
        # Face the water
        face_direction(page, adj[2])
        pos_before = get_player_position(page)
        press_game_key(page, "w")
        pos_after = get_player_position(page)
        assert pos_after == pos_before, \
            f"Player should not move into water: {pos_before} -> {pos_after}"

    def test_darkness_is_traversable(self, page):
        """Player can walk into a darkness (%) cell."""
        dark = find_cell_of_type(page, "%")
        if dark is None:
            pytest.skip("No darkness cells in maze")
        adj = find_adjacent_open_cell(page, dark[0], dark[1])
        if adj is None:
            pytest.skip("No accessible cell adjacent to darkness")
        if not navigate_to_cell(page, adj[0], adj[1]):
            pytest.skip("Could not reach cell adjacent to darkness")
        face_direction(page, adj[2])
        press_game_key(page, "w")
        pos_after = get_player_position(page)
        assert pos_after == (dark[0], dark[1]), \
            f"Player should be able to enter darkness cell at {dark}"


# ── Goal Detection ────────────────────────────────────────────────────────


class TestGoal:
    """Verify goal detection and messaging."""

    def test_goal_reached_api_initially_false(self, page):
        """isGoalReached() returns false at the start."""
        assert page.evaluate("() => window.game.isGoalReached()") is False

    def test_reaching_goal_shows_message(self, page):
        """Navigating to the goal cell shows a message in #game-message."""
        goal = find_cell_of_type(page, "!")
        assert goal is not None, "No goal cell in maze"
        reached = navigate_to_cell(page, goal[0], goal[1])
        if not reached:
            pytest.skip("Could not navigate to goal (maze too complex for auto-nav)")
        msg = page.evaluate("""() => {
            const el = document.querySelector('#game-message');
            return el ? el.textContent : '';
        }""")
        assert len(msg.strip()) > 0, "No congratulatory message displayed after reaching goal"

    def test_goal_reached_api(self, page):
        """After reaching the goal, isGoalReached() returns true."""
        goal = find_cell_of_type(page, "!")
        assert goal is not None, "No goal cell in maze"
        reached = navigate_to_cell(page, goal[0], goal[1])
        if not reached:
            pytest.skip("Could not navigate to goal")
        assert page.evaluate("() => window.game.isGoalReached()") is True


# ── Maze API ──────────────────────────────────────────────────────────────


class TestMazeAPI:
    """Verify the maze data API methods."""

    def test_maze_dimensions(self, page):
        """getMazeWidth() and getMazeHeight() return positive integers."""
        w = page.evaluate("() => window.game.getMazeWidth()")
        h = page.evaluate("() => window.game.getMazeHeight()")
        assert isinstance(w, int) and w > 0, f"Invalid maze width: {w}"
        assert isinstance(h, int) and h > 0, f"Invalid maze height: {h}"

    def test_maze_cell_types(self, page):
        """getMazeCell() returns valid cell type characters."""
        w = page.evaluate("() => window.game.getMazeWidth()")
        h = page.evaluate("() => window.game.getMazeHeight()")
        valid_types = {"#", ".", "%", "~", "!", "@"}
        # Sample a few cells
        for y in range(min(5, h)):
            for x in range(min(5, w)):
                cell = get_maze_cell(page, x, y)
                assert cell in valid_types, f"Invalid cell type '{cell}' at ({x}, {y})"

    def test_visited_cells_includes_start(self, page):
        """getVisitedCells() includes the starting position."""
        pos = get_player_position(page)
        visited = page.evaluate("() => window.game.getVisitedCells()")
        found = any(c["x"] == pos[0] and c["y"] == pos[1] for c in visited)
        assert found, f"Start position {pos} not in visited cells"
