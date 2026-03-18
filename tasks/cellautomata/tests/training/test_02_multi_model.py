"""Stage 2 training tests: Falling Sand, Langton's Ant, and multi-model support."""
import pytest

# ── Langton's Ant Rules ──────────────────────────────────────────────────

class TestLangtonRules:
    """Test Langton's Ant stepping mechanics."""

    def test_step_on_black_turns_left(self, sim_factory):
        """On black (1): turn left, flip cell, move forward."""
        s = sim_factory(model="langton")
        ant = s.get_ant()
        cx, cy = ant["x"], ant["y"]
        s.set_cell(cx, cy, 1)

        s.step()

        # Was N, on 1 -> turn left -> W, flip cell to 0, move west
        assert s.get_cell(cx, cy) == 0
        new_ant = s.get_ant()
        assert new_ant["direction"] == "W"
        assert new_ant["x"] == cx - 1
        assert new_ant["y"] == cy

    def test_default_ant_position(self, sim_factory):
        """Default ant is at center, facing N."""
        s = sim_factory(model="langton")
        ant = s.get_ant()
        assert ant["x"] == s.width // 2
        assert ant["y"] == s.height // 2
        assert ant["direction"] == "N"

    def test_set_get_ant(self, sim_factory):
        """set_ant/get_ant roundtrip."""
        s = sim_factory(model="langton")
        s.set_ant(3, 4, "S")
        ant = s.get_ant()
        assert ant == {"x": 3, "y": 4, "direction": "S"}

    def test_four_step_manual(self, sim_factory):
        """Manually verify 4 steps of Langton's ant on empty grid."""
        s = sim_factory(model="langton", width=10, height=10)
        cx, cy = s.width // 2, s.height // 2  # 5, 5

        # Step 1: at (5,5)=0 -> right -> E, flip to 1, move to (6,5)
        s.step()
        assert s.get_ant() == {"x": 6, "y": 5, "direction": "E"}
        assert s.get_cell(5, 5) == 1

        # Step 2: at (6,5)=0 -> right -> S, flip to 1, move to (6,6)
        s.step()
        assert s.get_ant() == {"x": 6, "y": 6, "direction": "S"}
        assert s.get_cell(6, 5) == 1

        # Step 3: at (6,6)=0 -> right -> W, flip to 1, move to (5,6)
        s.step()
        assert s.get_ant() == {"x": 5, "y": 6, "direction": "W"}
        assert s.get_cell(6, 6) == 1

        # Step 4: at (5,6)=0 -> right -> N, flip to 1, move to (5,5)
        s.step()
        assert s.get_ant() == {"x": 5, "y": 5, "direction": "N"}
        assert s.get_cell(5, 6) == 1


# ── Langton Boundary ─────────────────────────────────────────────────────

class TestLangtonBoundary:
    """Test Langton's ant boundary conditions."""

    def test_periodic_wraps_ant(self, sim_factory):
        """Ant wraps around periodic grid."""
        s = sim_factory(model="langton", boundary="periodic", width=10, height=10)
        # Ant at (0,0) facing W on white: turn right -> N, flip, move N
        # y=0 wraps to y=height-1
        s.set_ant(0, 0, "W")
        s.set_cell(0, 0, 0)
        s.step()
        ant = s.get_ant()
        assert ant["direction"] == "N"
        assert ant["y"] == s.height - 1

    def test_constant_raises_stop_iteration(self, sim_factory):
        """Ant leaving constant-boundary grid raises StopIteration."""
        s = sim_factory(model="langton", boundary="constant", width=10, height=10)
        # Ant at (0,0) facing N on black: turn left -> W, flip, move W -> off grid
        s.set_ant(0, 0, "N")
        s.set_cell(0, 0, 1)
        with pytest.raises(StopIteration):
            s.step()


# ── Model Errors ──────────────────────────────────────────────────────────

class TestModelErrors:
    """Test that model-specific methods raise TypeError on wrong model."""

    def test_topple_on_conway_raises(self, sim):
        with pytest.raises(TypeError):
            sim.topple()

    def test_is_stable_on_conway_raises(self, sim):
        with pytest.raises(TypeError):
            sim.is_stable()

    def test_get_ant_on_conway_raises(self, sim):
        with pytest.raises(TypeError):
            sim.get_ant()

    def test_set_ant_on_conway_raises(self, sim):
        with pytest.raises(TypeError):
            sim.set_ant(0, 0)

    def test_get_ant_on_sandpile_raises(self, sim_factory):
        s = sim_factory(model="sandpile")
        with pytest.raises(TypeError):
            s.get_ant()

    def test_topple_on_langton_raises(self, sim_factory):
        s = sim_factory(model="langton")
        with pytest.raises(TypeError):
            s.topple()


# ── Multi-Model UI ────────────────────────────────────────────────────────

class TestMultiModelUI:
    """Test model-selection dropdown in GUI."""

    def test_combo_has_three_items(self, main_window):
        from PySide6.QtWidgets import QComboBox
        combo = main_window.findChild(QComboBox, "combo_model")
        assert combo.count() == 3

    def test_switching_model_resets(self, main_window, qtbot):
        """Changing model dropdown resets the grid after stepping."""
        from PySide6.QtWidgets import QComboBox, QPushButton, QLabel
        from PySide6.QtCore import Qt

        # Run a few steps first so step count > 0
        btn_start = main_window.findChild(QPushButton, "btn_start")
        btn_stop = main_window.findChild(QPushButton, "btn_stop")
        lbl = main_window.findChild(QLabel, "lbl_step_count")
        qtbot.mouseClick(btn_start, Qt.LeftButton)
        qtbot.waitUntil(lambda: "0" not in lbl.text(), timeout=2000)
        qtbot.mouseClick(btn_stop, Qt.LeftButton)

        # Switch model — should reset step count to 0
        combo = main_window.findChild(QComboBox, "combo_model")
        combo.setCurrentIndex(1)
        assert "0" in lbl.text()


# ── Falling Sand Rules ──────────────────────────────────────────────────

class TestFallingSandRules:
    """Test basic falling-sand (sandpile) stepping mechanics."""

    def test_grain_on_flat_surface_stable(self, sim_factory):
        """A grain resting on a flat row of grains should not move."""
        s = sim_factory(model="sandpile", width=10, height=10, boundary="constant")
        # Floor row at y=9
        for x in range(3, 8):
            s.set_cell(x, 9, 1)
        # Grain sitting on the flat surface
        s.set_cell(5, 8, 1)

        s.step()

        assert s.get_cell(5, 8) == 1, "grain should stay on flat surface"
        # Surrounding cells remain unchanged
        for x in range(3, 8):
            assert s.get_cell(x, 9) == 1

    def test_grain_on_pyramid_tip_stable(self, sim_factory):
        """A grain at a 45-degree pyramidal apex (distance=2 both sides) stays."""
        s = sim_factory(model="sandpile", width=10, height=10, boundary="constant")
        # Floor: three grains providing lateral support at distance 2
        s.set_cell(4, 9, 1)
        s.set_cell(5, 9, 1)
        s.set_cell(6, 9, 1)
        # Column of support directly below
        s.set_cell(5, 8, 1)
        # Test grain at the tip — adjacent columns have support at distance 2
        s.set_cell(5, 7, 1)

        s.step()

        assert s.get_cell(5, 7) == 1, "grain at 45-degree tip should stay"
        assert s.get_cell(5, 8) == 1
        assert s.is_stable()

    def test_grain_slides_left_on_cliff(self, sim_factory):
        """Grain with a deep left gap (distance > 2) slides one cell left."""
        s = sim_factory(model="sandpile", width=10, height=10, boundary="constant")
        # Floor providing right-side support
        for x in range(4, 8):
            s.set_cell(x, 9, 1)
        # Stable support layer
        s.set_cell(5, 8, 1)
        s.set_cell(6, 8, 1)
        # More support below test grain
        s.set_cell(5, 7, 1)
        # Test grain: left column (x=4) has (4,9) at distance 9-6=3 > 2,
        # right column (x=6) has (6,8) at distance 8-6=2 <= 2 → slides left
        s.set_cell(5, 6, 1)

        s.step()

        assert s.get_cell(5, 6) == 0, "grain should have left its original cell"
        assert s.get_cell(4, 6) == 1, "grain should have slid one cell left"


# ── Falling Sand Stability ──────────────────────────────────────────────

class TestFallingSandStability:
    """Test is_stable() and topple() on sandpile grids."""

    def test_empty_grid_is_stable(self, sim_factory):
        """An empty sandpile grid is stable."""
        s = sim_factory(model="sandpile", width=10, height=10, boundary="constant")
        assert s.is_stable()

    def test_flat_surface_is_stable(self, sim_factory):
        """A grain on a flat surface is already stable."""
        s = sim_factory(model="sandpile", width=10, height=10, boundary="constant")
        for x in range(3, 8):
            s.set_cell(x, 9, 1)
        s.set_cell(5, 8, 1)
        assert s.is_stable()

    def test_unsupported_grain_is_not_stable(self, sim_factory):
        """A grain floating above empty space is not stable."""
        s = sim_factory(model="sandpile", width=10, height=10, boundary="constant")
        s.set_cell(5, 3, 1)  # floating grain, nothing below
        assert not s.is_stable()

    def test_topple_stabilizes_grid(self, sim_factory):
        """topple() runs until no grain would move; returns total move count."""
        s = sim_factory(model="sandpile", width=10, height=10, boundary="constant")
        s.set_cell(5, 3, 1)  # floating grain
        moves = s.topple()
        assert moves > 0, "at least one grain should have moved"
        assert s.is_stable(), "grid must be stable after topple()"
        # The grain should have settled on the floor row
        assert s.get_cell(5, 9) == 1
