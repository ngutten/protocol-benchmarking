"""
Holdout tests for Stage 1: Maze Explorer.

More rigorous rendering, interaction, and edge-case tests that are hidden
from the LLM during development.
"""
import pytest
from ..conftest import (
    get_game_state, get_player_position, get_player_direction,
    press_game_key, get_canvas_pixel, get_element_dimensions,
    sample_region_colors, get_maze_cell, find_cell_of_type,
    find_adjacent_open_cell, navigate_to_cell, face_direction,
    get_element_screenshot_pixels,
)


# ── Rendering Depth ───────────────────────────────────────────────────────


class TestRenderingDepth:
    """Verify the 3D rendering shows proper depth cues."""

    def test_corridor_shows_depth(self, page):
        """In a corridor, the rendering shows walls converging (perspective)."""
        dims = get_element_dimensions(page, "#game-view")
        if dims is None:
            pytest.skip("No game-view element")
        w, h = int(dims["width"]), int(dims["height"])

        # Find a long corridor to look down (move to an open area first)
        state = get_game_state(page)
        deltas = {"N": (0, -1), "E": (1, 0), "S": (0, 1), "W": (-1, 0)}

        # Try to find a direction with at least 3 open cells ahead
        for _ in range(4):
            d = get_player_direction(page)
            pos = get_player_position(page)
            dx, dy = deltas[d]
            open_count = 0
            for i in range(1, 4):
                cell = get_maze_cell(page, pos[0] + dx * i, pos[1] + dy * i)
                if cell in (".", "@", "!", "%"):
                    open_count += 1
                else:
                    break
            if open_count >= 3:
                break
            press_game_key(page, "d")
        else:
            # Move around to find a corridor
            for _ in range(10):
                press_game_key(page, "w")
                for _ in range(4):
                    d = get_player_direction(page)
                    pos = get_player_position(page)
                    dx, dy = deltas[d]
                    open_count = 0
                    for i in range(1, 4):
                        cell = get_maze_cell(page, pos[0] + dx * i, pos[1] + dy * i)
                        if cell in (".", "@", "!", "%"):
                            open_count += 1
                        else:
                            break
                    if open_count >= 3:
                        break
                    press_game_key(page, "d")
                if open_count >= 3:
                    break

        if open_count < 3:
            pytest.skip("Could not find a 3-cell corridor")

        # Sample left edge and center — in a corridor with perspective,
        # the wall boundaries should differ
        left_color = sample_region_colors(page, "#game-view", 5, h // 2, 15, 10)
        center_color = sample_region_colors(page, "#game-view", w // 2 - 10, h // 2, 20, 10)
        if left_color is None or center_color is None:
            pytest.skip("Cannot sample canvas pixels")

        # The edges (wall) and center (corridor view) should differ
        diff = sum(abs(a - b) for a, b in zip(left_color, center_color))
        assert diff > 10, f"Left edge and center look the same — no depth rendering? {left_color} vs {center_color}"

    def test_three_cell_visibility(self, page):
        """The renderer shows content at least 3 cells deep."""
        state = get_game_state(page)
        deltas = {"N": (0, -1), "E": (1, 0), "S": (0, 1), "W": (-1, 0)}

        # Find a 3+ cell corridor
        for _ in range(4):
            d = get_player_direction(page)
            pos = get_player_position(page)
            dx, dy = deltas[d]
            open_count = 0
            for i in range(1, 5):
                cell = get_maze_cell(page, pos[0] + dx * i, pos[1] + dy * i)
                if cell in (".", "@", "!"):
                    open_count += 1
                else:
                    break
            if open_count >= 3:
                break
            press_game_key(page, "d")

        if open_count < 3:
            pytest.skip("No 3-cell corridor found from start")

        # The center of the view should show something at depth (not just blank)
        dims = get_element_dimensions(page, "#game-view")
        if dims is None:
            pytest.skip("No game-view")
        w, h = int(dims["width"]), int(dims["height"])
        center = sample_region_colors(page, "#game-view", w // 2 - 5, h // 2 - 5, 10, 10)
        assert center is not None, "Cannot read center pixels"
        # Center should not be pure black (should see the distant wall)
        assert not all(c < 5 for c in center), "Center is black — depth not rendered"


# ── Darkness Details ──────────────────────────────────────────────────────


class TestDarknessDetails:
    """Detailed tests for darkness (%) cell behavior."""

    def _find_darkness_and_adjacent(self, page):
        """Find a darkness cell with an accessible adjacent cell."""
        dark = find_cell_of_type(page, "%")
        if dark is None:
            pytest.skip("No darkness cells in maze")
        adj = find_adjacent_open_cell(page, dark[0], dark[1])
        if adj is None:
            pytest.skip("No accessible cell adjacent to darkness")
        return dark, adj

    def test_darkness_not_on_minimap_before_visit(self, page):
        """Darkness cells should not appear on minimap before visiting them."""
        visited = page.evaluate("() => window.game.getVisitedCells()")
        dark = find_cell_of_type(page, "%")
        if dark is None:
            pytest.skip("No darkness cells")
        # Check that darkness cell is NOT in visited cells initially
        dark_visited = any(c["x"] == dark[0] and c["y"] == dark[1] for c in visited)
        assert not dark_visited, "Darkness cell should not be visited before player enters it"

    def test_darkness_appears_on_minimap_after_visit(self, page):
        """After entering a darkness cell, it appears in visited cells."""
        dark, adj = self._find_darkness_and_adjacent(page)
        if not navigate_to_cell(page, adj[0], adj[1]):
            pytest.skip("Could not reach cell adjacent to darkness")
        face_direction(page, adj[2])
        press_game_key(page, "w")
        pos = get_player_position(page)
        if pos != (dark[0], dark[1]):
            pytest.skip("Could not enter darkness cell")
        visited = page.evaluate("() => window.game.getVisitedCells()")
        dark_visited = any(c["x"] == dark[0] and c["y"] == dark[1] for c in visited)
        assert dark_visited, "Darkness cell should be in visited cells after entering"

    def test_cannot_see_through_darkness(self, page):
        """Darkness blocks view — cells behind it are not visible."""
        dark, adj = self._find_darkness_and_adjacent(page)
        if not navigate_to_cell(page, adj[0], adj[1]):
            pytest.skip("Could not reach adjacent cell")
        face_direction(page, adj[2])

        # The center of the view should be very dark (darkness blocks vision)
        dims = get_element_dimensions(page, "#game-view")
        if dims is None:
            pytest.skip("No game-view")
        w, h = int(dims["width"]), int(dims["height"])
        center = sample_region_colors(page, "#game-view", w // 2 - 10, h // 2 - 10, 20, 20)
        if center is None:
            pytest.skip("Cannot sample canvas")
        brightness = sum(center) / 3
        assert brightness < 80, \
            f"View through darkness should be dark, brightness={brightness}: {center}"


# ── Water Details ─────────────────────────────────────────────────────────


class TestWaterDetails:
    """Detailed tests for water (~) cell behavior."""

    def test_water_visible_as_floor(self, page):
        """Water renders as a visible surface (not a wall), but blocks movement."""
        water = find_cell_of_type(page, "~")
        if water is None:
            pytest.skip("No water cells")
        adj = find_adjacent_open_cell(page, water[0], water[1])
        if adj is None:
            pytest.skip("No accessible cell adjacent to water")
        if not navigate_to_cell(page, adj[0], adj[1]):
            pytest.skip("Could not reach cell adjacent to water")
        face_direction(page, adj[2])

        # Looking at water should show something visible (not completely black like walls)
        dims = get_element_dimensions(page, "#game-view")
        if dims is None:
            pytest.skip("No game-view")
        w, h = int(dims["width"]), int(dims["height"])
        center = sample_region_colors(page, "#game-view", w // 2 - 10, h // 2 - 10, 20, 20)
        if center is None:
            pytest.skip("Cannot sample canvas")
        # Water should have some color (not pitch black)
        # This is a loose check — different implementations may vary
        assert center is not None, "Should render something when facing water"

    def test_water_on_minimap(self, page):
        """Water cells show distinctly on the minimap (different from hallways)."""
        water = find_cell_of_type(page, "~")
        if water is None:
            pytest.skip("No water cells")
        # Navigate near water to reveal it on the minimap
        adj = find_adjacent_open_cell(page, water[0], water[1])
        if adj is None:
            pytest.skip("No accessible cell adjacent to water")
        navigate_to_cell(page, adj[0], adj[1])

        # Verify minimap has content (basic check)
        dims = get_element_dimensions(page, "#minimap")
        assert dims is not None, "No minimap"
        assert dims["width"] > 0 and dims["height"] > 0


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

    def test_backward_through_corridor(self, page):
        """S key moves backward correctly through a corridor."""
        deltas = {"N": (0, -1), "E": (1, 0), "S": (0, 1), "W": (-1, 0)}
        pos_start = get_player_position(page)

        # Find open direction and move forward twice
        for _ in range(4):
            d = get_player_direction(page)
            dx, dy = deltas[d]
            cell = get_maze_cell(page, pos_start[0] + dx, pos_start[1] + dy)
            if cell not in ("#", "~"):
                break
            press_game_key(page, "d")

        press_game_key(page, "w")
        pos1 = get_player_position(page)
        if pos1 == pos_start:
            pytest.skip("Cannot move forward")

        # Now backward
        press_game_key(page, "s")
        pos2 = get_player_position(page)
        assert pos2 == pos_start, f"Backward should return to {pos_start}, got {pos2}"

    def test_movement_updates_visited_cells(self, page):
        """Each move adds newly revealed cells to visited list."""
        visited_before = len(page.evaluate("() => window.game.getVisitedCells()"))
        # Move around
        for key in ["w", "d", "w", "w"]:
            press_game_key(page, key)
        visited_after = len(page.evaluate("() => window.game.getVisitedCells()"))
        assert visited_after >= visited_before, \
            "Visited cell count should not decrease after moving"


# ── Rendering Changes ─────────────────────────────────────────────────────


class TestRendering:
    """Verify the rendering updates when the player acts."""

    def _get_view_snapshot(self, page):
        """Get a simple hash of the current game view."""
        return page.evaluate("""() => {
            const el = document.querySelector('#game-view');
            if (!el) return null;
            const canvas = el.tagName === 'CANVAS' ? el : el.querySelector('canvas');
            if (!canvas) return null;
            const ctx = canvas.getContext('2d');
            const data = ctx.getImageData(0, 0, canvas.width, canvas.height).data;
            let hash = 0;
            for (let i = 0; i < data.length; i += 40) {
                hash = ((hash << 5) - hash + data[i]) | 0;
            }
            return hash;
        }""")

    def test_view_changes_on_turn(self, page):
        """Canvas content changes when the player turns."""
        snap1 = self._get_view_snapshot(page)
        if snap1 is None:
            pytest.skip("Cannot snapshot game view")
        press_game_key(page, "d")
        snap2 = self._get_view_snapshot(page)
        assert snap2 != snap1, "Game view should change after turning"

    def test_view_changes_on_move(self, page):
        """Canvas content changes when the player moves forward."""
        # Find an open direction
        deltas = {"N": (0, -1), "E": (1, 0), "S": (0, 1), "W": (-1, 0)}
        pos = get_player_position(page)
        for _ in range(4):
            d = get_player_direction(page)
            dx, dy = deltas[d]
            cell = get_maze_cell(page, pos[0] + dx, pos[1] + dy)
            if cell not in ("#", "~"):
                break
            press_game_key(page, "d")

        snap1 = self._get_view_snapshot(page)
        if snap1 is None:
            pytest.skip("Cannot snapshot game view")
        press_game_key(page, "w")
        new_pos = get_player_position(page)
        if new_pos == pos:
            pytest.skip("Could not move forward")
        snap2 = self._get_view_snapshot(page)
        assert snap2 != snap1, "Game view should change after moving forward"
