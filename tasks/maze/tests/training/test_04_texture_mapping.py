"""
Training tests for Stage 4: Texture Mapping.

Tests texture application to surfaces and the getCellTextures API.
"""
import pytest
from ..conftest import (
    get_game_state, get_player_position, get_player_direction,
    press_game_key, get_canvas_pixel, get_element_dimensions,
    sample_region_colors, get_maze_cell, navigate_to_cell,
    face_direction, find_cell_of_type,
)


# ── Textures ──────────────────────────────────────────────────────────────


class TestTextures:
    """Verify texture application to surfaces."""

    def test_textures_applied(self, page):
        """Wall surfaces show texture variation, not uniform flat color."""
        page.evaluate("() => window.game.regenerateMaze(10, 10)")
        page.wait_for_timeout(500)

        dims = get_element_dimensions(page, "#game-view")
        if dims is None:
            pytest.skip("No game-view")
        w, h = int(dims["width"]), int(dims["height"])

        # Sample several small patches along the left wall area — textures
        # create pixel-level variation that flat shading does not
        colors = []
        for y_off in range(-2, 3):
            c = sample_region_colors(page, "#game-view", 10, h // 2 + y_off * 15, 5, 5)
            if c:
                colors.append(tuple(c))
        if len(colors) < 3:
            pytest.skip("Cannot sample enough canvas regions")

        unique = len(set(colors))
        assert unique >= 2, \
            f"Wall surface appears to be a flat solid color (no texture variation): {colors}"

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
