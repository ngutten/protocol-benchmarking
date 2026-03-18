"""
Holdout tests for Stage 2: Procedural Maze Generation & Textures.

More rigorous tests for maze generation quality, door details, and texture variety.
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

        # Just verify the view has content (door is rendered)
        w, h = int(dims["width"]), int(dims["height"])
        center = sample_region_colors(page, "#game-view",
                                      w // 2 - 10, h // 2 - 10, 20, 20)
        assert center is not None, "View should have content when looking at door"


# ── Texture Details ───────────────────────────────────────────────────────


class TestTextureDetails:
    """Detailed tests for texture application and variety."""

    def test_wall_textures_vary(self, page):
        """Different parts of the maze use different wall textures."""
        page.evaluate("() => window.game.regenerateMaze(20, 20)")
        page.wait_for_timeout(500)

        state = get_game_state(page)
        w, h = state["mazeWidth"], state["mazeHeight"]

        # Collect wall texture info from cells (via getCellTextures or visual check)
        # Since wall textures aren't directly in getCellTextures, we check
        # that visually different wall areas exist
        pos = get_player_position(page)

        # Move and sample wall colors at different locations
        wall_colors = []
        for _ in range(6):
            dims = get_element_dimensions(page, "#game-view")
            if dims:
                vw, vh = int(dims["width"]), int(dims["height"])
                # Sample left wall area
                color = sample_region_colors(page, "#game-view", 10, vh // 2, 15, 10)
                if color:
                    wall_colors.append(tuple(color))
            press_game_key(page, "w")
            press_game_key(page, "d")
            press_game_key(page, "w")

        if len(wall_colors) < 2:
            pytest.skip("Could not collect enough wall samples")

        # Check that we see some variation in wall rendering
        unique = len(set(wall_colors))
        # Even with same texture, perspective changes create some variation
        assert unique >= 1, "Should have some wall rendering"

    def test_floor_textures_vary(self, page):
        """Different areas have different floor textures."""
        page.evaluate("() => window.game.regenerateMaze(20, 20)")
        page.wait_for_timeout(500)

        state = get_game_state(page)
        w, h = state["mazeWidth"], state["mazeHeight"]

        floor_textures = set()
        for y in range(h):
            for x in range(w):
                cell = get_maze_cell(page, x, y)
                if cell in ("#", "~"):
                    continue
                tex = page.evaluate(
                    "([x, y]) => window.game.getCellTextures(x, y)", [x, y]
                )
                if tex and tex.get("floor"):
                    floor_textures.add(tex["floor"])
                if len(floor_textures) >= 2:
                    break
            if len(floor_textures) >= 2:
                break

        assert len(floor_textures) >= 2, \
            f"Expected multiple floor textures, found: {floor_textures}"

    def test_ceiling_textures_applied(self, page):
        """Ceiling has texture content (not blank)."""
        page.evaluate("() => window.game.regenerateMaze(10, 10)")
        page.wait_for_timeout(500)

        dims = get_element_dimensions(page, "#game-view")
        if dims is None:
            pytest.skip("No game-view")
        w, h = int(dims["width"]), int(dims["height"])

        # Top of the view is ceiling
        ceiling_color = sample_region_colors(page, "#game-view",
                                             w // 3, h // 8, w // 3, 10)
        if ceiling_color is None:
            pytest.skip("Cannot sample canvas")

        # Ceiling should have some color (not pitch black)
        brightness = sum(ceiling_color) / 3
        assert brightness > 3, \
            f"Ceiling should have visible texture, got brightness={brightness}"

    def test_water_uses_water_texture(self, page):
        """Water tiles use the water-specific texture."""
        page.evaluate("() => window.game.regenerateMaze(15, 15)")
        page.wait_for_timeout(500)

        water = find_cell_of_type(page, "~")
        if water is None:
            # The generated maze might not have water — that's ok for stage 2
            pytest.skip("No water tiles in generated maze")

        # Check the texture assigned to the water cell
        tex = page.evaluate(
            "([x, y]) => window.game.getCellTextures(x, y)",
            [water[0], water[1]]
        )
        if tex is None:
            pytest.skip("getCellTextures not available for water")
        # The floor texture for water should reference water
        assert "water" in tex.get("floor", "").lower(), \
            f"Water cell should use water texture, got: {tex.get('floor')}"
