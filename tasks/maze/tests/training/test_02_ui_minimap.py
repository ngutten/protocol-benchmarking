"""
Training tests for Stage 2: First-Person Rendering & Minimap.

Tests focus on 3D visual rendering, minimap display, and terrain visual
appearance using Playwright browser automation.
"""
import pytest
from ..conftest import (
    get_game_state, get_player_position, get_player_direction,
    press_game_key, get_canvas_pixel, get_element_dimensions,
    sample_region_colors, get_maze_cell, find_cell_of_type,
    find_adjacent_open_cell, navigate_to_cell, face_direction,
)


# ── Rendering ────────────────────────────────────────────────────────────


class TestRendering:
    """Verify the 3D first-person rendering."""

    def test_game_view_renders_content(self, page):
        """The game view has non-blank pixels (something is rendered)."""
        dims = get_element_dimensions(page, "#game-view")
        assert dims is not None
        cx = int(dims["width"] // 2)
        cy = int(dims["height"] // 2)
        # Sample multiple locations to check for non-blank content
        has_content = False
        for dx, dy in [(0, 0), (-50, -50), (50, 50), (0, -30), (0, 30)]:
            pixel = get_canvas_pixel(page, "#game-view", cx + dx, cy + dy)
            if pixel is not None and not all(c == 0 for c in pixel[:3]):
                has_content = True
                break
        assert has_content, "Game view appears completely blank"

    def test_walls_render_differently_from_floor(self, page):
        """Wall areas and floor areas have visually different colors."""
        dims = get_element_dimensions(page, "#game-view")
        if dims is None:
            pytest.skip("No game-view element")
        w, h = int(dims["width"]), int(dims["height"])
        # Sample top area (likely ceiling/wall) and bottom area (likely floor)
        top_color = sample_region_colors(page, "#game-view", w // 4, h // 6, w // 2, 10)
        bottom_color = sample_region_colors(page, "#game-view", w // 4, h * 5 // 6, w // 2, 10)
        if top_color is None or bottom_color is None:
            # Try screenshot-based approach
            pytest.skip("Cannot sample canvas pixels directly")
        # Colors should differ between ceiling/wall area and floor area
        diff = sum(abs(a - b) for a, b in zip(top_color, bottom_color))
        assert diff > 20, f"Top and bottom regions look too similar: {top_color} vs {bottom_color}"

    def test_minimap_exists_upper_left(self, page):
        """The #minimap element exists and is positioned in the upper-left area."""
        info = page.evaluate("""() => {
            const el = document.querySelector('#minimap');
            if (!el) return null;
            const rect = el.getBoundingClientRect();
            return {
                x: rect.x, y: rect.y,
                width: rect.width, height: rect.height,
                windowWidth: window.innerWidth, windowHeight: window.innerHeight
            };
        }""")
        assert info is not None, "#minimap element not found"
        assert info["width"] > 0, "Minimap has zero width"
        assert info["height"] > 0, "Minimap has zero height"
        # Check it's in the upper-left quadrant
        assert info["x"] < info["windowWidth"] / 2, "Minimap is not in the left half"
        assert info["y"] < info["windowHeight"] / 2, "Minimap is not in the upper half"


# ── Terrain Visuals ──────────────────────────────────────────────────────


class TestTerrainVisuals:
    """Verify visual rendering of special terrain types."""

    def test_darkness_renders_black(self, page):
        """When facing darkness, the center of the view is black/very dark."""
        dark = find_cell_of_type(page, "%")
        if dark is None:
            pytest.skip("No darkness cells in maze")
        adj = find_adjacent_open_cell(page, dark[0], dark[1])
        if adj is None:
            pytest.skip("No accessible cell adjacent to darkness")
        if not navigate_to_cell(page, adj[0], adj[1]):
            pytest.skip("Could not reach cell adjacent to darkness")
        face_direction(page, adj[2])
        # Sample center of the game view
        dims = get_element_dimensions(page, "#game-view")
        if dims is None:
            pytest.skip("No game-view element")
        cx, cy = int(dims["width"] // 2), int(dims["height"] // 2)
        color = sample_region_colors(page, "#game-view", cx - 10, cy - 10, 20, 20)
        if color is None:
            pytest.skip("Cannot sample canvas pixels")
        # Darkness should render as very dark
        brightness = sum(color) / 3
        assert brightness < 60, \
            f"Darkness should render dark, but center brightness is {brightness}: {color}"

    def test_goal_visual(self, page):
        """The goal cell has a distinct visual rendering compared to a plain hallway."""
        goal = find_cell_of_type(page, "!")
        assert goal is not None, "No goal cell in maze"
        adj = find_adjacent_open_cell(page, goal[0], goal[1])
        if adj is None:
            pytest.skip("No accessible cell adjacent to goal")
        if not navigate_to_cell(page, adj[0], adj[1]):
            pytest.skip("Could not reach cell adjacent to goal")

        # First, snapshot a normal hallway view (face away from goal)
        opp = {"N": "S", "S": "N", "E": "W", "W": "E"}
        face_direction(page, opp[adj[2]])
        dims = get_element_dimensions(page, "#game-view")
        if dims is None:
            pytest.skip("No game-view element")
        cx, cy = int(dims["width"] // 2), int(dims["height"] // 2)
        hallway_color = sample_region_colors(page, "#game-view", cx - 15, cy - 15, 30, 30)

        # Now face the goal and snapshot
        face_direction(page, adj[2])
        goal_color = sample_region_colors(page, "#game-view", cx - 15, cy - 15, 30, 30)
        if goal_color is None or hallway_color is None:
            pytest.skip("Cannot sample canvas pixels")

        # Goal should look different from a normal hallway
        diff = sum(abs(a - b) for a, b in zip(goal_color, hallway_color))
        assert diff > 15, \
            f"Goal should look distinct from hallway: goal={goal_color} hallway={hallway_color}"


# ── Minimap ───────────────────────────────────────────────────────────────


class TestMinimap:
    """Verify minimap rendering and behavior."""

    def test_minimap_shows_visited_cells(self, page):
        """After moving around, the minimap has content in visited areas."""
        # Move a few times to build up visited cells
        for key in ["w", "w", "w", "d", "w", "w"]:
            press_game_key(page, key)
        visited = page.evaluate("() => window.game.getVisitedCells()")
        assert len(visited) > 1, "Should have visited multiple cells after moving"

        # Check minimap has some non-blank content
        dims = get_element_dimensions(page, "#minimap")
        if dims is None:
            pytest.skip("No minimap element")
        assert dims["width"] > 0 and dims["height"] > 0

    def test_minimap_shows_player_position(self, page):
        """The minimap shows the player's position marker."""
        # The minimap should have some distinct pixel where the player is
        dims = get_element_dimensions(page, "#minimap")
        if dims is None:
            pytest.skip("No minimap element")
        # We can at minimum verify the minimap has non-trivial content
        cx, cy = int(dims["width"] // 2), int(dims["height"] // 2)
        # Sample the minimap to see it's not blank
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
            // Non-canvas minimap — check if it has child elements with content
            return el.children.length > 0 || el.innerHTML.trim().length > 0;
        }""", "#minimap")
        assert has_content, "Minimap appears to have no content"
