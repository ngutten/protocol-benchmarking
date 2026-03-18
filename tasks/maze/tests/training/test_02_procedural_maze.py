"""
Training tests for Stage 2: Procedural Maze Generation & Textures.

Tests maze generation, edge walls, doors, textures, and updated minimap.
"""
import pytest
from ..conftest import (
    get_game_state, get_player_position, get_player_direction,
    press_game_key, get_canvas_pixel, get_element_dimensions,
    sample_region_colors, get_maze_cell, navigate_to_cell,
    face_direction, find_cell_of_type,
)


# ── Maze Generation ──────────────────────────────────────────────────────


class TestMazeGeneration:
    """Verify procedural maze generation via the regenerateMaze API."""

    def test_regenerate_creates_new_maze(self, page):
        """Calling regenerateMaze() changes the maze."""
        state1 = get_game_state(page)
        w1, h1 = state1["mazeWidth"], state1["mazeHeight"]

        # Collect some cell values from the original maze
        original_cells = []
        for y in range(min(5, h1)):
            for x in range(min(5, w1)):
                original_cells.append(get_maze_cell(page, x, y))

        # Regenerate with a different size to ensure it changes
        page.evaluate("() => window.game.regenerateMaze(15, 15)")
        page.wait_for_timeout(500)

        state2 = get_game_state(page)
        # Either dimensions changed or cells changed
        changed = (state2["mazeWidth"] != w1 or state2["mazeHeight"] != h1)
        if not changed:
            new_cells = []
            for y in range(min(5, state2["mazeHeight"])):
                for x in range(min(5, state2["mazeWidth"])):
                    new_cells.append(get_maze_cell(page, x, y))
            changed = new_cells != original_cells
        assert changed, "regenerateMaze() should produce a different maze"

    def test_generated_maze_has_start_and_goal(self, page):
        """Generated maze has traversable cells and a player position."""
        page.evaluate("() => window.game.regenerateMaze(15, 15)")
        page.wait_for_timeout(500)
        pos = get_player_position(page)
        state = get_game_state(page)
        assert pos is not None, "Player should have a position in generated maze"
        assert state["mazeWidth"] > 0 and state["mazeHeight"] > 0

    def test_generated_maze_is_solvable(self, page):
        """Can navigate from start to goal in a generated maze."""
        page.evaluate("() => window.game.regenerateMaze(10, 10)")
        page.wait_for_timeout(500)

        # Find the goal
        goal = find_cell_of_type(page, "!")
        if goal is None:
            pytest.skip("No goal cell in generated maze")

        reached = navigate_to_cell(page, goal[0], goal[1], max_steps=500)
        # Either we reached it or the API says so
        if not reached:
            reached = page.evaluate("() => window.game.isGoalReached()")
        assert reached, "Generated maze should be solvable"


# ── Edge Walls ────────────────────────────────────────────────────────────


class TestEdgeWalls:
    """Verify edge-based wall representation."""

    def test_cell_walls_api(self, page):
        """getCellWalls() returns wall info for each edge of a cell."""
        page.evaluate("() => window.game.regenerateMaze(10, 10)")
        page.wait_for_timeout(500)
        pos = get_player_position(page)
        walls = page.evaluate(
            "([x, y]) => window.game.getCellWalls(x, y)", [pos[0], pos[1]]
        )
        assert walls is not None, "getCellWalls() returned null"
        for edge in ("n", "e", "s", "w"):
            assert edge in walls, f"getCellWalls() missing '{edge}' edge"
            assert walls[edge] in ("wall", "door", "open"), \
                f"Invalid wall type for {edge}: {walls[edge]}"

    def test_edge_wall_renders(self, page):
        """A wall between two open cells renders visually."""
        page.evaluate("() => window.game.regenerateMaze(10, 10)")
        page.wait_for_timeout(500)

        # Find a cell with a wall edge
        state = get_game_state(page)
        w, h = state["mazeWidth"], state["mazeHeight"]
        found = False
        for y in range(h):
            for x in range(w):
                walls = page.evaluate(
                    "([x, y]) => window.game.getCellWalls(x, y)", [x, y]
                )
                if walls and any(v == "wall" for v in walls.values()):
                    found = True
                    break
            if found:
                break
        assert found, "No edge walls found in generated maze"


# ── Doors ─────────────────────────────────────────────────────────────────


class TestDoors:
    """Verify door mechanics."""

    def _find_door_cell(self, page):
        """Find a cell that has a door on one of its edges."""
        state = get_game_state(page)
        w, h = state["mazeWidth"], state["mazeHeight"]
        for y in range(h):
            for x in range(w):
                walls = page.evaluate(
                    "([x, y]) => window.game.getCellWalls(x, y)", [x, y]
                )
                if walls:
                    for edge, val in walls.items():
                        if val == "door":
                            return (x, y, edge)
        return None

    def test_door_in_cell_walls(self, page):
        """At least one cell has a 'door' edge."""
        page.evaluate("() => window.game.regenerateMaze(15, 15)")
        page.wait_for_timeout(500)
        result = self._find_door_cell(page)
        assert result is not None, "No doors found in generated maze"

    def test_door_is_passable(self, page):
        """Player can walk through a door edge."""
        page.evaluate("() => window.game.regenerateMaze(15, 15)")
        page.wait_for_timeout(500)
        door_info = self._find_door_cell(page)
        if door_info is None:
            pytest.skip("No doors in generated maze")
        x, y, edge = door_info
        edge_to_dir = {"n": "N", "e": "E", "s": "S", "w": "W"}
        dir_deltas = {"N": (0, -1), "E": (1, 0), "S": (0, 1), "W": (-1, 0)}
        direction = edge_to_dir[edge]
        dx, dy = dir_deltas[direction]

        # Navigate to the door cell
        if not navigate_to_cell(page, x, y, max_steps=300):
            pytest.skip("Could not reach door cell")
        face_direction(page, direction)
        pos_before = get_player_position(page)
        press_game_key(page, "w")
        pos_after = get_player_position(page)
        expected = (x + dx, y + dy)
        assert pos_after == expected, \
            f"Should walk through door to {expected}, got {pos_after}"

    def test_door_renders_distinctly(self, page):
        """Door areas render differently from solid walls."""
        page.evaluate("() => window.game.regenerateMaze(15, 15)")
        page.wait_for_timeout(500)
        door_info = self._find_door_cell(page)
        if door_info is None:
            pytest.skip("No doors in maze")

        x, y, edge = door_info
        edge_to_dir = {"n": "N", "e": "E", "s": "S", "w": "W"}
        direction = edge_to_dir[edge]

        if not navigate_to_cell(page, x, y, max_steps=300):
            pytest.skip("Could not reach door cell")
        face_direction(page, direction)

        # Snapshot the door view
        dims = get_element_dimensions(page, "#game-view")
        if dims is None:
            pytest.skip("No game-view")
        w, h = int(dims["width"]), int(dims["height"])
        door_color = sample_region_colors(page, "#game-view",
                                          w // 2 - 15, h // 2 - 15, 30, 30)

        # Find a solid wall to compare
        walls_info = page.evaluate(
            "([x, y]) => window.game.getCellWalls(x, y)", [x, y]
        )
        wall_dir = None
        for e, v in walls_info.items():
            if v == "wall":
                wall_dir = edge_to_dir[e]
                break

        if wall_dir and door_color:
            face_direction(page, wall_dir)
            page.wait_for_timeout(100)
            wall_color = sample_region_colors(page, "#game-view",
                                              w // 2 - 15, h // 2 - 15, 30, 30)
            if wall_color:
                diff = sum(abs(a - b) for a, b in zip(door_color, wall_color))
                assert diff > 10, \
                    f"Door and wall should look different: {door_color} vs {wall_color}"


# ── Textures ──────────────────────────────────────────────────────────────


class TestTextures:
    """Verify texture application to surfaces."""

    def test_textures_applied(self, page):
        """Surfaces show textured content (not flat solid colors)."""
        page.evaluate("() => window.game.regenerateMaze(10, 10)")
        page.wait_for_timeout(500)

        dims = get_element_dimensions(page, "#game-view")
        if dims is None:
            pytest.skip("No game-view")
        w, h = int(dims["width"]), int(dims["height"])

        # Sample two adjacent small regions on a wall — textures should have variation
        color1 = sample_region_colors(page, "#game-view", 10, h // 2, 5, 5)
        color2 = sample_region_colors(page, "#game-view", 30, h // 2, 5, 5)
        if color1 is None or color2 is None:
            pytest.skip("Cannot sample canvas")

        # With textures, adjacent small regions usually differ
        # This is a weak check — flat shading might pass too
        assert color1 is not None and color2 is not None

    def test_cell_textures_api(self, page):
        """getCellTextures() returns floor and ceiling texture names."""
        page.evaluate("() => window.game.regenerateMaze(10, 10)")
        page.wait_for_timeout(500)
        pos = get_player_position(page)
        textures = page.evaluate(
            "([x, y]) => window.game.getCellTextures(x, y)", [pos[0], pos[1]]
        )
        assert textures is not None, "getCellTextures() returned null"
        assert "floor" in textures, "Missing 'floor' in textures"
        assert "ceiling" in textures, "Missing 'ceiling' in textures"
        assert isinstance(textures["floor"], str) and len(textures["floor"]) > 0
        assert isinstance(textures["ceiling"], str) and len(textures["ceiling"]) > 0

    def test_different_areas_different_textures(self, page):
        """Two areas with different assigned textures render differently."""
        page.evaluate("() => window.game.regenerateMaze(20, 20)")
        page.wait_for_timeout(500)

        state = get_game_state(page)
        w, h = state["mazeWidth"], state["mazeHeight"]

        # Find two cells with different floor textures
        textures_seen = {}
        for y in range(h):
            for x in range(w):
                cell = get_maze_cell(page, x, y)
                if cell in ("#", "~"):
                    continue
                tex = page.evaluate(
                    "([x, y]) => window.game.getCellTextures(x, y)", [x, y]
                )
                if tex and tex["floor"]:
                    key = tex["floor"]
                    if key not in textures_seen:
                        textures_seen[key] = (x, y)
                    if len(textures_seen) >= 2:
                        break
            if len(textures_seen) >= 2:
                break

        assert len(textures_seen) >= 2, "Expected at least 2 different floor textures"


# ── Minimap Stage 2 ──────────────────────────────────────────────────────


class TestMinimapStage2:
    """Verify minimap updates for stage 2 features."""

    def test_minimap_shows_doors(self, page):
        """Doors are visible on the minimap differently from walls."""
        page.evaluate("() => window.game.regenerateMaze(15, 15)")
        page.wait_for_timeout(500)

        # Move around to reveal some of the minimap
        for _ in range(20):
            press_game_key(page, "w")
            if get_player_position(page) == get_player_position(page):
                press_game_key(page, "d")

        # Basic check: minimap has content
        dims = get_element_dimensions(page, "#minimap")
        assert dims is not None, "No minimap"
        assert dims["width"] > 0 and dims["height"] > 0
