"""
Shared fixtures for CellAutomata benchmark tests.

Unlike other benchmark tasks (fluidsim, minidb, plotcurve) which communicate via
subprocess JSON protocols, CellAutomata tests import the module directly.
GUI tests use pytest-qt with headless Qt.
"""
import sys
import os
import pytest


# ---------------------------------------------------------------------------
# Workspace discovery: the harness sets ENGINE_CMD to
#   "cd <workspace> && python3 cellautomata.py"
# We parse the workspace path and add it to sys.path so tests can
#   `from cellautomata import Simulation`.
# ---------------------------------------------------------------------------
ENGINE_CMD_ENV = "CELLAUTOMATA_ENGINE_CMD"
_engine_cmd = os.environ.get(ENGINE_CMD_ENV, os.environ.get("MINIDB_ENGINE_CMD", ""))
if _engine_cmd and "cd " in _engine_cmd:
    _workspace = _engine_cmd.split("&&")[0].replace("cd ", "").strip()
    sys.path.insert(0, _workspace)
else:
    sys.path.insert(0, os.getcwd())

# Headless Qt BEFORE any PySide6 import
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


# ---------------------------------------------------------------------------
# Library fixtures (no GUI dependency)
# ---------------------------------------------------------------------------

@pytest.fixture
def sim():
    """Fresh 16x16 periodic Conway simulation."""
    from cellautomata import Simulation
    return Simulation(width=16, height=16, model="conway", boundary="periodic")


@pytest.fixture
def sim_factory():
    """Factory: call with kwargs to create custom Simulation."""
    from cellautomata import Simulation

    def _make(**kwargs):
        defaults = {"width": 16, "height": 16}
        defaults.update(kwargs)
        return Simulation(**defaults)

    return _make


@pytest.fixture
def sim_large():
    """256x256 Conway simulation for heavier tests."""
    from cellautomata import Simulation
    return Simulation(width=256, height=256)


# ---------------------------------------------------------------------------
# GUI fixtures (require PySide6 + pytest-qt)
# ---------------------------------------------------------------------------

@pytest.fixture
def main_window(qtbot):
    """PySide6 main window for UI tests."""
    pytest.importorskip("PySide6")
    from cellautomata import CellAutomataWindow
    window = CellAutomataWindow()
    qtbot.addWidget(window)
    window.show()
    return window
