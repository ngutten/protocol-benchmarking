"""
Holdout tests for Stage 4: Texture Mapping.

Detailed tests for texture application and variety.
"""
import pytest
from ..conftest import (
    get_game_state, get_player_position, get_player_direction,
    press_game_key, get_canvas_pixel, get_element_dimensions,
    sample_region_colors, get_maze_cell, navigate_to_cell,
    face_direction, find_cell_of_type,
)


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

        # Check that we see variation in wall rendering across the maze
        unique = len(set(wall_colors))
        assert unique >= 2, \
            f"Expected visual variation in walls from different textures, got {unique} unique samples from {len(wall_colors)}"

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
            # The generated maze might not have water — that's ok for stage 4
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
