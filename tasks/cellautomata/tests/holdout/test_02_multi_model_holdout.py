"""Stage 2 holdout tests: Falling Sand, Langton's Ant — rigorous correctness checks."""
import pytest


# ── Langton Analytical ────────────────────────────────────────────────────

class TestLangtonAnalytical:
    """Analytical tests for Langton's ant."""

    def test_population_after_4_steps(self, sim_factory):
        """First 4 steps on empty grid visit 4 distinct cells, all flipped to 1."""
        s = sim_factory(model="langton", width=30, height=30)
        s.step(4)
        # The ant traces a square on an empty grid: 4 distinct cells flipped to 1
        assert s.count_alive() == 4

    def test_ant_returns_to_start_after_4_steps(self, sim_factory):
        """On an empty grid, Langton's ant returns to start after exactly 4 steps."""
        s = sim_factory(model="langton", width=64, height=64)
        start = s.get_ant()
        s.step(4)
        ant = s.get_ant()
        # After 4 right turns on empty cells, ant completes a square
        assert ant["x"] == start["x"]
        assert ant["y"] == start["y"]
        assert ant["direction"] == start["direction"]

    def test_langton_population_is_count_of_ones(self, sim_factory):
        """For Langton, count_alive() returns the count of cells equal to 1."""
        s = sim_factory(model="langton", width=20, height=20)
        # After 4 steps on empty grid, ant flips 4 cells to 1
        # (first 4 steps visit distinct cells on empty grid)
        s.step(4)
        pop = s.count_alive()
        grid = s.get_grid()
        manual_count = sum(1 for row in grid for c in row if c == 1)
        assert pop == manual_count


# ── Multi-Model UI ───────────────────────────────────────────────────────

class TestMultiModelUI:
    """Test model-switching UI behavior."""

    def test_model_switch_preserves_dimensions(self, main_window, qtbot):
        """Switching model via dropdown should preserve grid dimensions."""
        from PySide6.QtWidgets import QComboBox, QWidget
        combo = main_window.findChild(QComboBox, "combo_model")
        assert combo is not None

        grid_view = main_window.findChild(QWidget, "grid_view")
        size_before = (grid_view.width(), grid_view.height())

        # Switch to sandpile then back to conway
        combo.setCurrentIndex(1)
        combo.setCurrentIndex(0)

        # Grid display dimensions should be preserved
        size_after = (grid_view.width(), grid_view.height())
        assert size_after == size_before

    def test_model_switch_resets_step_count(self, main_window, qtbot):
        """Switching model resets the step count to 0."""
        from PySide6.QtWidgets import QComboBox, QPushButton, QLabel
        from PySide6.QtCore import Qt

        # Run a few steps first
        btn_start = main_window.findChild(QPushButton, "btn_start")
        btn_stop = main_window.findChild(QPushButton, "btn_stop")
        qtbot.mouseClick(btn_start, Qt.LeftButton)
        qtbot.wait(200)
        qtbot.mouseClick(btn_stop, Qt.LeftButton)

        # Switch model
        combo = main_window.findChild(QComboBox, "combo_model")
        combo.setCurrentIndex(1)
        lbl = main_window.findChild(QLabel, "lbl_step_count")
        assert "0" in lbl.text()


# ── Falling Sand Simultaneous ───────────────────────────────────────────

class TestFallingSandSimultaneous:
    """Test simultaneous movement and collision resolution in sandpile."""

    def test_stacked_grains_fall_sequentially(self, sim_factory):
        """Two vertically stacked grains in thin air: bottom falls first,
        top stays (equal lateral distances), then top falls next step."""
        s = sim_factory(model="sandpile", width=10, height=10, boundary="constant")
        # Two grains stacked with empty space below
        s.set_cell(5, 4, 1)  # top grain
        s.set_cell(5, 5, 1)  # bottom grain

        # --- Step 1 ---
        # Bottom grain: empty below → falls to (5,6)
        # Top grain: sees (5,5) occupied in initial state → checks lateral;
        #   both sides equally empty → stays (equal-distance special case)
        s.step()

        assert s.get_cell(5, 4) == 1, "top grain stays (equal lateral distances)"
        assert s.get_cell(5, 5) == 0, "bottom grain vacated"
        assert s.get_cell(5, 6) == 1, "bottom grain fell one cell"

        # --- Step 2 ---
        # Top grain: now (5,5) is empty below → falls
        s.step()

        assert s.get_cell(5, 4) == 0, "top grain fell away"
        assert s.get_cell(5, 5) == 1, "top grain fell to (5,5)"

    def test_left_right_collision(self, sim_factory):
        """Two grains on opposite cliff edges slide toward the same empty
        column and collide; one occupies the target, the other stacks below."""
        s = sim_factory(model="sandpile", width=10, height=10, boundary="constant")

        # Wide floor for stable support
        for x in range(1, 9):
            s.set_cell(x, 9, 1)
        # Left support pyramid: y=8 x=2,3,4 ; y=7 x=3,4
        for x in (2, 3, 4):
            s.set_cell(x, 8, 1)
        for x in (3, 4):
            s.set_cell(x, 7, 1)
        # Right support: y=8 x=6,7 ; y=7 x=6
        for x in (6, 7):
            s.set_cell(x, 8, 1)
        s.set_cell(6, 7, 1)

        # Sliding grains on the cliff edges — both target (5,6)
        s.set_cell(4, 6, 1)  # left grain: right col distance > 2, slides right
        s.set_cell(6, 6, 1)  # right grain: left col distance > 2, slides left

        s.step()

        # Original positions vacated
        assert s.get_cell(4, 6) == 0, "left grain moved"
        assert s.get_cell(6, 6) == 0, "right grain moved"
        # Collision at (5,6): one grain at target, excess stacked below
        assert s.get_cell(5, 6) == 1, "one grain occupies target cell"
        assert s.get_cell(5, 7) == 1, "other grain stacked one cell below"

    def test_falling_and_sliding_collision(self, sim_factory):
        """A free-falling grain and a laterally sliding grain both target the
        same cell; collision stacks them vertically."""
        s = sim_factory(model="sandpile", width=10, height=10, boundary="constant")

        # Stable support for the sliding grain — pyramid in columns 1-5
        for x in range(1, 6):
            s.set_cell(x, 9, 1)
        for x in (2, 3, 4):
            s.set_cell(x, 8, 1)
        for x in (3, 4):
            s.set_cell(x, 7, 1)

        # Sliding grain at (4,6): left col 3 has (3,7) at d=1,
        # right col 5 has (5,9) at d=3 > 2 → slides right to (5,6)
        s.set_cell(4, 6, 1)

        # Falling grain at (5,5): nothing below → falls to (5,6)
        s.set_cell(5, 5, 1)

        s.step()

        # Original positions vacated
        assert s.get_cell(4, 6) == 0, "sliding grain moved"
        assert s.get_cell(5, 5) == 0, "falling grain moved"
        # Collision at (5,6): one at target, one stacked below
        assert s.get_cell(5, 6) == 1, "one grain at collision target"
        assert s.get_cell(5, 7) == 1, "other grain stacked below"
