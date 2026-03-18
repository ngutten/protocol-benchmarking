"""Stage 1 holdout tests: Conway's Game of Life — rigorous correctness checks."""
import pytest


# ── Known Patterns ────────────────────────────────────────────────────────

class TestKnownPatterns:
    """Test well-known Conway patterns for correctness."""

    def test_beehive_still_life(self, sim):
        """Beehive is a period-1 still life."""
        for x, y in [(4, 3), (5, 3), (3, 4), (6, 4), (4, 5), (5, 5)]:
            sim.set_cell(x, y, 1)
        grid_before = sim.get_grid()
        sim.step()
        assert sim.get_grid() == grid_before

    def test_loaf_still_life(self, sim):
        """Loaf is a period-1 still life."""
        for x, y in [(5, 3), (6, 3), (4, 4), (7, 4), (5, 5), (7, 5), (6, 6)]:
            sim.set_cell(x, y, 1)
        grid_before = sim.get_grid()
        sim.step()
        assert sim.get_grid() == grid_before

    def test_toad_oscillator(self, sim):
        """Toad is a period-2 oscillator."""
        for x, y in [(5, 5), (6, 5), (7, 5), (4, 6), (5, 6), (6, 6)]:
            sim.set_cell(x, y, 1)
        grid_t0 = sim.get_grid()
        sim.step()
        grid_t1 = sim.get_grid()
        assert grid_t1 != grid_t0
        sim.step()
        assert sim.get_grid() == grid_t0

    def test_beacon_oscillator(self, sim):
        """Beacon is a period-2 oscillator."""
        for x, y in [(3, 3), (4, 3), (3, 4), (6, 5), (5, 6), (6, 6)]:
            sim.set_cell(x, y, 1)
        grid_t0 = sim.get_grid()
        sim.step(2)
        assert sim.get_grid() == grid_t0

    def test_r_pentomino_grows(self, sim_factory):
        """R-pentomino grows from 5 cells and is not a still life."""
        s = sim_factory(width=32, height=32)
        r_pent = [(1, 0), (2, 0), (0, 1), (1, 1), (1, 2)]
        s.load_pattern(r_pent, offset_x=14, offset_y=14)
        assert s.count_alive() == 5
        s.step(20)
        # R-pentomino grows rapidly; population should exceed initial 5
        assert s.count_alive() > 5
        # It should still be evolving (not settled into a still life yet)
        hist = s.get_population_history()
        assert hist[-1] != hist[-2], "Pattern should not have stabilized by step 20"


# ── Edge Cases ────────────────────────────────────────────────────────────

class TestEdgeCases:
    """Test degenerate grid configurations."""

    def test_empty_grid_stays_empty(self, sim):
        sim.step(10)
        assert sim.count_alive() == 0

    def test_full_grid_all_die(self, sim):
        """Grid of all 1s on periodic boundary: every cell has 8 neighbors -> all die."""
        grid = [[1] * sim.width for _ in range(sim.height)]
        sim.set_grid(grid)
        sim.step()
        assert sim.count_alive() == 0

    def test_two_adjacent_cells_die(self, sim):
        """Two horizontally adjacent cells: each has 1 neighbor -> both die."""
        sim.set_cell(5, 5, 1)
        sim.set_cell(6, 5, 1)
        sim.step()
        assert sim.get_cell(5, 5) == 0
        assert sim.get_cell(6, 5) == 0


# ── Boundary Edge Cases ──────────────────────────────────────────────────

class TestBoundaryEdgeCases:
    """Test boundary behavior at grid corners and edges."""

    def test_corner_periodic_neighbor_count(self, sim):
        """Cell at (0,0) on periodic grid has 8 neighbors including wraps."""
        w, h = sim.width, sim.height
        neighbors = [
            (w - 1, h - 1), (0, h - 1), (1, h - 1),
            (w - 1, 0),                  (1, 0),
            (w - 1, 1),     (0, 1),      (1, 1),
        ]
        # Set exactly 3 neighbors -> (0,0) should be born
        for x, y in neighbors[:3]:
            sim.set_cell(x, y, 1)
        sim.step()
        assert sim.get_cell(0, 0) == 1

    def test_corner_constant_boundary(self, sim_factory):
        """Cell at corner of constant-boundary grid sees only 3 on-grid neighbors."""
        s = sim_factory(boundary="constant")
        s.set_cell(1, 0, 1)
        s.set_cell(0, 1, 1)
        s.set_cell(1, 1, 1)
        s.step()
        assert s.get_cell(0, 0) == 1

    def test_edge_wrapping_blinker(self, sim):
        """Blinker crossing the edge wraps correctly on periodic grid."""
        w = sim.width
        sim.set_cell(w - 1, 5, 1)
        sim.set_cell(0, 5, 1)
        sim.set_cell(1, 5, 1)
        grid_t0 = sim.get_grid()
        sim.step(2)
        assert sim.get_grid() == grid_t0


# ── Population Dynamics ───────────────────────────────────────────────────

class TestPopulationDynamics:
    """Test population counting and history consistency."""

    def test_history_matches_count(self, sim):
        """Each population history entry matches count_alive at that step."""
        sim.set_cell(1, 1, 1)
        sim.set_cell(2, 1, 1)
        sim.set_cell(1, 2, 1)
        sim.set_cell(2, 2, 1)
        for _ in range(10):
            sim.step()
            hist = sim.get_population_history()
            assert hist[-1] == sim.count_alive()

    def test_still_life_constant_population(self, sim):
        """Block: population should be 4 after every step."""
        sim.set_cell(1, 1, 1)
        sim.set_cell(2, 1, 1)
        sim.set_cell(1, 2, 1)
        sim.set_cell(2, 2, 1)
        sim.step(10)
        hist = sim.get_population_history()
        assert all(p == 4 for p in hist)

    def test_oscillator_population(self, sim):
        """Blinker: population is 3 at every step."""
        sim.set_cell(5, 5, 1)
        sim.set_cell(6, 5, 1)
        sim.set_cell(7, 5, 1)
        sim.step(10)
        hist = sim.get_population_history()
        assert all(p == 3 for p in hist)


# ── Grid Integrity ────────────────────────────────────────────────────────

class TestGridIntegrity:
    """Test that get_grid/set_grid return independent copies."""

    def test_get_grid_returns_copy(self, sim):
        """Mutating the returned grid must not affect the simulation."""
        sim.set_cell(5, 5, 1)
        grid = sim.get_grid()
        grid[5][5] = 0
        assert sim.get_cell(5, 5) == 1

    def test_set_grid_copies_input(self, sim):
        """Mutating the source grid after set_grid must not affect the simulation."""
        grid = [[0] * sim.width for _ in range(sim.height)]
        grid[3][3] = 1
        sim.set_grid(grid)
        grid[3][3] = 0
        assert sim.get_cell(3, 3) == 1


# ── UI Interaction ────────────────────────────────────────────────────────

class TestUIInteraction:
    """Test that the GUI drives the simulation correctly."""

    def test_auto_stepping_advances_simulation(self, main_window, qtbot):
        """Clicking Start should begin auto-stepping; Stop should halt it."""
        from PySide6.QtWidgets import QPushButton, QLabel
        from PySide6.QtCore import Qt

        btn_start = main_window.findChild(QPushButton, "btn_start")
        btn_stop = main_window.findChild(QPushButton, "btn_stop")
        lbl = main_window.findChild(QLabel, "lbl_step_count")

        # Initially at step 0
        assert "0" in lbl.text()

        qtbot.mouseClick(btn_start, Qt.LeftButton)
        # Wait for at least one step to fire
        qtbot.waitUntil(lambda: "0" not in lbl.text() or lbl.text().strip() != "0",
                        timeout=2000)
        qtbot.mouseClick(btn_stop, Qt.LeftButton)

        # Step count should have advanced past 0
        text = lbl.text()
        digits = "".join(c for c in text if c.isdigit())
        assert int(digits) > 0, f"Step count did not advance: '{text}'"

    def test_reset_clears_after_stepping(self, main_window, qtbot):
        """Reset should clear the grid and zero the step count after auto-stepping."""
        from PySide6.QtWidgets import QPushButton, QLabel
        from PySide6.QtCore import Qt

        btn_start = main_window.findChild(QPushButton, "btn_start")
        btn_stop = main_window.findChild(QPushButton, "btn_stop")
        btn_reset = main_window.findChild(QPushButton, "btn_reset")
        lbl_step = main_window.findChild(QLabel, "lbl_step_count")
        lbl_pop = main_window.findChild(QLabel, "lbl_population")

        # Run a few steps
        qtbot.mouseClick(btn_start, Qt.LeftButton)
        qtbot.wait(200)
        qtbot.mouseClick(btn_stop, Qt.LeftButton)

        # Reset
        qtbot.mouseClick(btn_reset, Qt.LeftButton)
        assert "0" in lbl_step.text()
        assert "0" in lbl_pop.text()

    def test_labels_update_after_step(self, main_window, qtbot):
        """Step count and population labels should update after a step is taken."""
        from PySide6.QtWidgets import QPushButton, QLabel
        from PySide6.QtCore import Qt

        lbl_step = main_window.findChild(QLabel, "lbl_step_count")
        lbl_pop = main_window.findChild(QLabel, "lbl_population")

        # Initially at step 0
        assert "0" in lbl_step.text()

        # Run a few auto-steps
        btn_start = main_window.findChild(QPushButton, "btn_start")
        btn_stop = main_window.findChild(QPushButton, "btn_stop")
        qtbot.mouseClick(btn_start, Qt.LeftButton)
        qtbot.waitUntil(lambda: "0" not in lbl_step.text(), timeout=2000)
        qtbot.mouseClick(btn_stop, Qt.LeftButton)

        # Step label should show a non-zero count
        digits = "".join(c for c in lbl_step.text() if c.isdigit())
        assert int(digits) > 0
        # Population label should still contain a digit
        assert any(c.isdigit() for c in lbl_pop.text())
