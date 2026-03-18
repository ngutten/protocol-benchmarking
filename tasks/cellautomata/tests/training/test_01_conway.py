"""Stage 1 training tests: Conway's Game of Life — library API and basic GUI."""
import pytest


# ── Creation & Properties ─────────────────────────────────────────────────

class TestSimulationCreation:
    """Test Simulation construction and read-only properties."""

    def test_default_creation(self, sim_factory):
        s = sim_factory()
        assert s.width == 16
        assert s.height == 16
        assert s.model == "conway"
        assert s.boundary == "periodic"

    def test_custom_dimensions(self, sim_factory):
        s = sim_factory(width=32, height=64)
        assert s.width == 32
        assert s.height == 64

    def test_constant_boundary(self, sim_factory):
        s = sim_factory(boundary="constant")
        assert s.boundary == "constant"

    def test_invalid_model_raises(self, sim_factory):
        with pytest.raises(ValueError):
            sim_factory(model="unknown")


# ── Grid Operations ───────────────────────────────────────────────────────

class TestGridOperations:
    """Test cell get/set, grid get/set, toggle, and clear."""

    def test_initial_grid_all_zero(self, sim):
        for row in sim.get_grid():
            assert all(c == 0 for c in row)

    def test_set_get_cell(self, sim):
        sim.set_cell(3, 4, 1)
        assert sim.get_cell(3, 4) == 1

    def test_toggle_cell(self, sim):
        assert sim.get_cell(0, 0) == 0
        sim.toggle_cell(0, 0)
        assert sim.get_cell(0, 0) == 1
        sim.toggle_cell(0, 0)
        assert sim.get_cell(0, 0) == 0

    def test_out_of_bounds_get(self, sim):
        with pytest.raises(IndexError):
            sim.get_cell(sim.width, 0)

    def test_out_of_bounds_set(self, sim):
        with pytest.raises(IndexError):
            sim.set_cell(-1, 0, 1)

    def test_set_grid_get_grid(self, sim):
        grid = [[0] * sim.width for _ in range(sim.height)]
        grid[2][3] = 1
        sim.set_grid(grid)
        assert sim.get_cell(3, 2) == 1

    def test_set_grid_wrong_dims(self, sim):
        with pytest.raises(ValueError):
            sim.set_grid([[0, 0], [0, 0]])  # wrong size for 16x16

    def test_clear_resets_grid(self, sim):
        sim.set_cell(5, 5, 1)
        sim.step()
        sim.clear()
        assert sim.count_alive() == 0
        assert sim.get_step_count() == 0


# ── Conway Rules ──────────────────────────────────────────────────────────

class TestConwayRules:
    """Test B3/S23 rule, synchronous update, known patterns."""

    def test_blinker_oscillates(self, sim):
        """Blinker (period 2): horizontal -> vertical -> horizontal."""
        # Horizontal blinker at row 5
        sim.set_cell(4, 5, 1)
        sim.set_cell(5, 5, 1)
        sim.set_cell(6, 5, 1)
        grid_before = sim.get_grid()

        sim.step()  # -> vertical
        sim.step()  # -> horizontal again
        assert sim.get_grid() == grid_before

    def test_block_still_life(self, sim):
        """Block is a period-1 still life."""
        sim.set_cell(1, 1, 1)
        sim.set_cell(2, 1, 1)
        sim.set_cell(1, 2, 1)
        sim.set_cell(2, 2, 1)
        grid_before = sim.get_grid()

        sim.step()
        assert sim.get_grid() == grid_before

    def test_birth_exactly_three(self, sim):
        """Dead cell with exactly 3 live neighbors comes alive."""
        # L-shape: 3 neighbors around (2,2) that is dead
        sim.set_cell(1, 1, 1)
        sim.set_cell(2, 1, 1)
        sim.set_cell(1, 2, 1)
        sim.step()
        assert sim.get_cell(2, 2) == 1

    def test_death_underpopulation(self, sim):
        """Live cell with <2 neighbors dies."""
        sim.set_cell(8, 8, 1)  # lone cell
        sim.step()
        assert sim.get_cell(8, 8) == 0

    def test_death_overpopulation(self, sim):
        """Live cell with >3 neighbors dies."""
        # Plus shape: center has 4 neighbors
        sim.set_cell(5, 5, 1)
        sim.set_cell(4, 5, 1)
        sim.set_cell(6, 5, 1)
        sim.set_cell(5, 4, 1)
        sim.set_cell(5, 6, 1)
        sim.step()
        assert sim.get_cell(5, 5) == 0  # center had 4 neighbors

    def test_glider_four_steps(self, sim):
        """Glider translates one cell diagonally after 4 steps."""
        # Standard glider
        sim.set_cell(1, 0, 1)
        sim.set_cell(2, 1, 1)
        sim.set_cell(0, 2, 1)
        sim.set_cell(1, 2, 1)
        sim.set_cell(2, 2, 1)

        alive_before = set()
        for y in range(sim.height):
            for x in range(sim.width):
                if sim.get_cell(x, y):
                    alive_before.add((x, y))

        sim.step(4)

        alive_after = set()
        for y in range(sim.height):
            for x in range(sim.width):
                if sim.get_cell(x, y):
                    alive_after.add((x, y))

        # Glider should have translated by (1, 1)
        expected = {((x + 1) % sim.width, (y + 1) % sim.height)
                    for x, y in alive_before}
        assert alive_after == expected


# ── Boundary Conditions ───────────────────────────────────────────────────

class TestBoundaryConditions:
    """Test periodic and constant boundary behavior."""

    def test_periodic_wrapping(self, sim):
        """Cell at edge affects cell on opposite edge (periodic)."""
        # Place cells near right edge; neighbor count should wrap
        w = sim.width
        sim.set_cell(w - 1, 5, 1)
        sim.set_cell(w - 1, 6, 1)
        sim.set_cell(w - 1, 7, 1)
        sim.step()
        # Blinker wraps: should affect column 0
        assert sim.get_cell(0, 6) == 1

    def test_periodic_glider_wraps(self, sim):
        """Glider wraps around periodic grid and returns."""
        sim.set_cell(1, 0, 1)
        sim.set_cell(2, 1, 1)
        sim.set_cell(0, 2, 1)
        sim.set_cell(1, 2, 1)
        sim.set_cell(2, 2, 1)
        pop_before = sim.count_alive()

        # Run many steps; glider shouldn't die on periodic grid
        sim.step(4 * sim.width)
        assert sim.count_alive() == pop_before

    def test_constant_boundary(self, sim_factory):
        """Constant boundary: cells outside grid treated as 0."""
        s = sim_factory(boundary="constant")
        # Blinker at edge: one neighbor is outside (dead)
        s.set_cell(0, 5, 1)
        s.set_cell(0, 6, 1)
        s.set_cell(0, 7, 1)
        s.step()
        # With constant boundary, (width-1, 6) should NOT get a neighbor
        # from the left blinker wrapping
        assert s.get_cell(s.width - 1, 6) == 0


# ── Step & History ────────────────────────────────────────────────────────

class TestStepAndHistory:
    """Test step counting and population history."""

    def test_step_increments_count(self, sim):
        sim.step()
        assert sim.get_step_count() == 1

    def test_step_n(self, sim):
        sim.step(5)
        assert sim.get_step_count() == 5

    def test_step_n_matches_individual(self, sim_factory):
        """step(n) produces same grid as n individual step(1) calls."""
        s1 = sim_factory()
        s2 = sim_factory()
        # Same initial pattern
        for x, y in [(1, 0), (2, 1), (0, 2), (1, 2), (2, 2)]:
            s1.set_cell(x, y, 1)
            s2.set_cell(x, y, 1)

        s1.step(10)
        for _ in range(10):
            s2.step()

        assert s1.get_grid() == s2.get_grid()

    def test_step_zero_raises(self, sim):
        with pytest.raises(ValueError):
            sim.step(0)

    def test_population_history_length(self, sim):
        sim.set_cell(1, 1, 1)
        sim.set_cell(2, 1, 1)
        sim.set_cell(1, 2, 1)
        sim.set_cell(2, 2, 1)
        sim.step(5)
        assert len(sim.get_population_history()) == 5

    def test_count_alive(self, sim):
        sim.set_cell(0, 0, 1)
        sim.set_cell(1, 1, 1)
        sim.set_cell(2, 2, 1)
        assert sim.count_alive() == 3


# ── Pattern Loading ───────────────────────────────────────────────────────

class TestLoadPattern:
    """Test load_pattern with offsets and wrapping."""

    def test_load_glider(self, sim):
        glider = [(0, 1), (1, 2), (2, 0), (2, 1), (2, 2)]
        sim.load_pattern(glider)
        for x, y in glider:
            assert sim.get_cell(x, y) == 1
        assert sim.count_alive() == 5

    def test_load_with_offset(self, sim):
        pattern = [(0, 0), (1, 0), (0, 1)]
        sim.load_pattern(pattern, offset_x=5, offset_y=5)
        assert sim.get_cell(5, 5) == 1
        assert sim.get_cell(6, 5) == 1
        assert sim.get_cell(5, 6) == 1

    def test_pattern_wraps_periodic(self, sim):
        """Pattern coordinates wrap on periodic grid."""
        w, h = sim.width, sim.height
        pattern = [(w - 1, h - 1)]
        sim.load_pattern(pattern, offset_x=1, offset_y=1)
        # (w-1+1) % w == 0, (h-1+1) % h == 0
        assert sim.get_cell(0, 0) == 1


# ── GUI (Basic) ───────────────────────────────────────────────────────────

class TestUI:
    """Test that GUI widgets exist and basic interactions work."""

    def test_required_widgets_exist(self, main_window):
        """All spec-required widgets must be present with correct objectNames."""
        from PySide6.QtWidgets import QPushButton, QWidget, QLabel
        assert main_window.findChild(QPushButton, "btn_start") is not None
        assert main_window.findChild(QPushButton, "btn_stop") is not None
        assert main_window.findChild(QPushButton, "btn_reset") is not None
        assert main_window.findChild(QWidget, "grid_view") is not None
        assert main_window.findChild(QLabel, "lbl_step_count") is not None
        assert main_window.findChild(QLabel, "lbl_population") is not None

    def test_reset_clears_grid(self, main_window, qtbot):
        """Clicking reset should clear the simulation."""
        from PySide6.QtWidgets import QPushButton, QLabel
        from PySide6.QtCore import Qt
        btn_reset = main_window.findChild(QPushButton, "btn_reset")
        qtbot.mouseClick(btn_reset, Qt.LeftButton)
        # After reset, population should be 0
        lbl = main_window.findChild(QLabel, "lbl_population")
        assert "0" in lbl.text()

    def test_window_resize_grid_follows(self, main_window, qtbot):
        """Resizing the window should resize the grid_view proportionally.

        The grid_view must remain the dominant widget and grow/shrink with
        the window so that cells stay at a usable size.
        """
        from PySide6.QtCore import QSize
        from PySide6.QtWidgets import QWidget

        grid_view = main_window.findChild(QWidget, "grid_view")
        assert grid_view is not None

        # Record original grid_view size
        orig_gv_w = grid_view.width()
        orig_gv_h = grid_view.height()

        # Grow the window by 200px in each dimension
        new_size = QSize(main_window.width() + 200, main_window.height() + 200)
        main_window.resize(new_size)
        qtbot.waitUntil(lambda: main_window.size() == new_size, timeout=1000)

        # grid_view should have grown
        assert grid_view.width() > orig_gv_w, (
            f"grid_view width did not grow after window resize "
            f"({grid_view.width()} vs original {orig_gv_w})"
        )
        assert grid_view.height() > orig_gv_h, (
            f"grid_view height did not grow after window resize "
            f"({grid_view.height()} vs original {orig_gv_h})"
        )

        # Shrink the window
        smaller_size = QSize(main_window.width() - 400, main_window.height() - 400)
        main_window.resize(smaller_size)
        qtbot.waitUntil(lambda: main_window.size() == smaller_size, timeout=1000)

        # grid_view should have shrunk
        assert grid_view.width() < orig_gv_w, (
            f"grid_view width did not shrink after window resize "
            f"({grid_view.width()} vs original {orig_gv_w})"
        )
        assert grid_view.height() < orig_gv_h, (
            f"grid_view height did not shrink after window resize "
            f"({grid_view.height()} vs original {orig_gv_h})"
        )
