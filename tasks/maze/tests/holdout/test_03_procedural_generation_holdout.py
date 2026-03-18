"""
Holdout tests for Stage 3: Edge Walls, Doors & Procedural Maze Generation.

More rigorous tests for maze generation quality and door details.
"""
import pytest
from ..conftest import (
    get_game_state, get_player_position, get_player_direction,
    press_game_key, get_canvas_pixel, get_element_dimensions,
    sample_region_colors, get_maze_cell, navigate_to_cell,
    face_direction, find_cell_of_type,
)


# ── Maze Generation Quality ──────────────────────────────────────────────


class TestMazeGenerationQuality:
    """Test the quality and correctness of procedural maze generation."""

    def test_maze_connectivity(self, page):
        """All open cells should be reachable from the start (connected maze)."""
        page.evaluate("() => window.game.regenerateMaze(10, 10)")
        page.wait_for_timeout(500)

        # Use BFS from the player start to check reachability
        result = page.evaluate("""() => {
            const pos = window.game.getPlayerPosition();
            const w = window.game.getMazeWidth();
            const h = window.game.getMazeHeight();
            const visited = new Set();
            const queue = [[pos.x, pos.y]];
            visited.add(pos.x + ',' + pos.y);

            while (queue.length > 0) {
                const [cx, cy] = queue.shift();
                const walls = window.game.getCellWalls(cx, cy);
                const dirs = {n: [0, -1], e: [1, 0], s: [0, 1], w: [-1, 0]};
                for (const [dir, [dx, dy]] of Object.entries(dirs)) {
                    if (walls[dir] === 'open' || walls[dir] === 'door') {
                        const nx = cx + dx, ny = cy + dy;
                        const key = nx + ',' + ny;
                        if (nx >= 0 && nx < w && ny >= 0 && ny < h && !visited.has(key)) {
                            visited.add(key);
                            queue.push([nx, ny]);
                        }
                    }
                }
            }

            // Count all non-wall cells
            let totalOpen = 0;
            for (let y = 0; y < h; y++) {
                for (let x = 0; x < w; x++) {
                    const cell = window.game.getMazeCell(x, y);
                    if (cell !== '#') totalOpen++;
                }
            }
            return {reachable: visited.size, totalOpen: totalOpen};
        }""")
        assert result["reachable"] >= result["totalOpen"], \
            f"Only {result['reachable']}/{result['totalOpen']} open cells reachable — maze not fully connected"

    def test_multiple_regenerations_differ(self, page):
        """Calling regenerateMaze multiple times produces different mazes."""
        mazes = []
        for _ in range(3):
            page.evaluate("() => window.game.regenerateMaze(10, 10)")
            page.wait_for_timeout(300)
            # Snapshot first row of cells
            w = page.evaluate("() => window.game.getMazeWidth()")
            row = []
            for x in range(w):
                row.append(get_maze_cell(page, x, 0))
            mazes.append(tuple(row))

        unique = len(set(mazes))
        assert unique >= 2, f"Expected different mazes but got {unique} unique out of 3"

    def test_maze_has_reasonable_size(self, page):
        """Generated maze is at least the requested size."""
        page.evaluate("() => window.game.regenerateMaze(12, 8)")
        page.wait_for_timeout(500)
        state = get_game_state(page)
        assert state["mazeWidth"] >= 12, f"Maze width {state['mazeWidth']} < 12"
        assert state["mazeHeight"] >= 8, f"Maze height {state['mazeHeight']} < 8"

    def test_generated_maze_has_goal(self, page):
        """Generated maze includes a goal cell."""
        page.evaluate("() => window.game.regenerateMaze(12, 12)")
        page.wait_for_timeout(500)
        goal = find_cell_of_type(page, "!")
        assert goal is not None, "Generated maze should have a goal cell"


# ── Door Details ──────────────────────────────────────────────────────────


class TestDoorDetails:
    """Detailed tests for door rendering and behavior."""

    def _find_door(self, page):
        """Find a door edge in the maze."""
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

    def test_door_visual_is_door_like(self, page):
        """Door area has visual characteristics distinct from open corridor."""
        page.evaluate("() => window.game.regenerateMaze(15, 15)")
        page.wait_for_timeout(500)
        door = self._find_door(page)
        if door is None:
            pytest.skip("No doors in maze")

        x, y, edge = door
        edge_to_dir = {"n": "N", "e": "E", "s": "S", "w": "W"}
        direction = edge_to_dir[edge]

        if not navigate_to_cell(page, x, y, max_steps=300):
            pytest.skip("Could not reach door cell")
        face_direction(page, direction)

        dims = get_element_dimensions(page, "#game-view")
        if dims is None:
            pytest.skip("No game-view")
        w, h = int(dims["width"]), int(dims["height"])

        # The door should have some visual rendering in the center
        center = sample_region_colors(page, "#game-view",
                                      w // 2 - 15, h // 2 - 15, 30, 30)
        assert center is not None, "Should render door view"
        # Door shouldn't be pitch black or pure white
        brightness = sum(center) / 3
        assert 5 < brightness < 250, \
            f"Door should have visible rendering, brightness={brightness}"

    def test_door_blocks_view_like_wall(self, page):
        """Door renders opaque like a wall when viewed from distance."""
        page.evaluate("() => window.game.regenerateMaze(15, 15)")
        page.wait_for_timeout(500)
        door = self._find_door(page)
        if door is None:
            pytest.skip("No doors in maze")

        x, y, edge = door
        edge_to_dir = {"n": "N", "e": "E", "s": "S", "w": "W"}
        dir_deltas = {"N": (0, -1), "E": (1, 0), "S": (0, 1), "W": (-1, 0)}
        direction = edge_to_dir[edge]
        # Move to the opposite side of the door (one cell back)
        opp = {"N": "S", "E": "W", "S": "N", "W": "E"}
        back_dir = opp[direction]
        bdx, bdy = dir_deltas[back_dir]

        # Navigate to cell on this side of door, one step back
        if not navigate_to_cell(page, x + bdx, y + bdy, max_steps=300):
            if not navigate_to_cell(page, x, y, max_steps=300):
                pytest.skip("Could not reach near door")

        face_direction(page, direction)
        dims = get_element_dimensions(page, "#game-view")
        if dims is None:
            pytest.skip("No game-view")

        # Verify the door renders as a visible opaque surface (not pitch black / transparent)
        w, h = int(dims["width"]), int(dims["height"])
        center = sample_region_colors(page, "#game-view",
                                      w // 2 - 10, h // 2 - 10, 20, 20)
        if center is None:
            pytest.skip("Cannot sample canvas")
        brightness = sum(center) / 3
        assert brightness > 5, \
            f"Door should render as a visible opaque surface, got brightness={brightness}: {center}"
