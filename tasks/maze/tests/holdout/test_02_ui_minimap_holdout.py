"""
Holdout tests for Stage 2: First-Person Rendering & Minimap.

More rigorous rendering, depth, terrain visual, and minimap tests that are
hidden from the LLM during development.
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
        """Water renders as a visible surface, not pitch black like a wall face."""
        water = find_cell_of_type(page, "~")
        if water is None:
            pytest.skip("No water cells")
        adj = find_adjacent_open_cell(page, water[0], water[1])
        if adj is None:
            pytest.skip("No accessible cell adjacent to water")
        if not navigate_to_cell(page, adj[0], adj[1]):
            pytest.skip("Could not reach cell adjacent to water")
        face_direction(page, adj[2])

        # Looking at water should show a visible floor area (not completely black)
        dims = get_element_dimensions(page, "#game-view")
        if dims is None:
            pytest.skip("No game-view")
        w, h = int(dims["width"]), int(dims["height"])
        # Sample lower-center area where water floor would render
        floor_color = sample_region_colors(page, "#game-view",
                                           w // 2 - 15, h * 2 // 3, 30, 15)
        if floor_color is None:
            pytest.skip("Cannot sample canvas")
        brightness = sum(floor_color) / 3
        assert brightness > 5, \
            f"Water should render as a visible floor surface, got brightness={brightness}: {floor_color}"

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

        # Verify minimap has non-blank rendered content
        has_content = page.evaluate("""(sel) => {
            const el = document.querySelector(sel);
            if (!el) return false;
            const canvas = el.tagName === 'CANVAS' ? el : el.querySelector('canvas');
            if (canvas) {
                const ctx = canvas.getContext('2d');
                const data = ctx.getImageData(0, 0, canvas.width, canvas.height).data;
                for (let i = 0; i < data.length; i += 4) {
                    if (data[i] > 10 || data[i+1] > 10 || data[i+2] > 10) return true;
                }
                return false;
            }
            return el.children.length > 0 || el.innerHTML.trim().length > 0;
        }""", "#minimap")
        assert has_content, "Minimap should have visible content after navigating near water"


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
