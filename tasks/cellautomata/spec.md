# CellAutomata: Cellular Automaton Simulator

## Overview

Implement a cellular automaton simulator as both a Python library and a PySide6 GUI
application. The module `cellautomata.py` must be importable (`from cellautomata
import Simulation`) and runnable as a standalone GUI (`python3 cellautomata.py`).

Supported models: Conway's Game of Life, Falling Sand, and Langton's Ant.

## Module & Entry Point

- **File:** `cellautomata.py` (single file)
- **GUI entry:** `python3 cellautomata.py`
- **Import:** `from cellautomata import Simulation, CellAutomataWindow`

## Library API

### `Simulation` class

```python
class Simulation:
    def __init__(self, width=256, height=256, model="conway", boundary="periodic")

    # Grid operations
    def get_cell(self, x, y) -> int
    def set_cell(self, x, y, value: int)
    def toggle_cell(self, x, y)          # 0<->1 flip
    def clear(self)                       # all cells to 0, reset step count
    def get_grid(self) -> list[list[int]] # [row][col], returns a copy
    def set_grid(self, grid: list[list[int]])

    # Simulation
    def step(self, n: int = 1)            # advance n generations
    def get_step_count(self) -> int

    # Analysis
    def count_alive(self) -> int
    def get_population_history(self) -> list[int]  # count after each step() call

    # Pattern loading
    def load_pattern(self, pattern: list[tuple[int, int]], offset_x=0, offset_y=0)

    # Properties (read-only)
    width: int
    height: int
    model: str       # "conway", "sandpile", "langton"
    boundary: str    # "periodic", "constant"

    # Falling Sand (model="sandpile")
    def topple(self) -> int       # run to stability, return total grain-move events
    def is_stable(self) -> bool   # True if no grain would move

    # Langton's Ant (model="langton")
    def get_ant(self) -> dict     # {"x": int, "y": int, "direction": str}
    def set_ant(self, x, y, direction="N")  # direction: N/E/S/W
```

### Model Rules

**Conway (model="conway")**: Binary grid (0 or 1). Birth/survival rule B3/S23 with
8-connected (Moore) neighborhood. Synchronous update: all cells update simultaneously
based on the previous generation.

**Falling Sand (model="sandpile")**: The Falling Sand model should work as follows: We have grains (state=1) 
which fall downwards if unsupported from below. If the cell below a grain has state=1, then we look to the left
and right and count how far down we must go until we hit a boundary or a state=1 cell in each
direction, with a distance of zero implying adjacency at the same height, a distance of one being 
just below that, and so on. If those distances are both 2 or less (e.g. a 45 degree angle=2, 
a flat surface=1, or supported by an adjacent grain in that direction=0) then the grain stays 
in place. Otherwise, the grain moves horizontally either to the left or right based on which 
distance is greater. There is a special case where the distances are equal, in which case the 
grain should not fall. Another special case is if two grains would enter the same cell 
(e.g. from left and right) then one of them moves below (which should be empty space because distance>2). 
All movements are computed from the grid state at the start of the iteration and occur simultaneously. 

**Langton's Ant (model="langton")**: Binary grid (0 or 1) plus an ant with position
(x, y) and direction (N/E/S/W). Each step: at the ant's current cell, if cell is 0
turn right 90 degrees, if cell is 1 turn left 90 degrees; then flip the cell (0<->1);
then move forward one cell. Default ant position: center of grid, facing N. Constant
boundary: raises `StopIteration` if the ant would move off the grid. Periodic
boundary: ant wraps to opposite edge.

### Error Handling

- Out-of-bounds `set_cell`/`get_cell`: `IndexError`
- Wrong-dimension `set_grid`: `ValueError`
- `step(n)` with n < 1: `ValueError`
- `topple()`/`is_stable()` on non-falling-sand: `TypeError`
- `get_ant()`/`set_ant()` on non-langton: `TypeError`
- Unknown model name: `ValueError`

## GUI

### Window Class

`CellAutomataWindow` — a `QMainWindow` subclass.

### Widget Object Names

| Widget             | objectName       | Type        |
|--------------------|------------------|-------------|
| Start button       | `btn_start`      | QPushButton |
| Stop button        | `btn_stop`       | QPushButton |
| Reset button       | `btn_reset`      | QPushButton |
| Grid display       | `grid_view`      | QWidget     |
| Step count label   | `lbl_step_count` | QLabel      |
| Population label   | `lbl_population` | QLabel      |
| Model dropdown     | `combo_model`    | QComboBox   |

### GUI Behaviors

- Clicking the grid toggles cells.
- **Start** begins auto-stepping on a timer.
- **Stop** pauses auto-stepping.
- **Reset** calls `clear()` on the simulation.
- Default: 64x64 periodic Conway.
- Switching model via dropdown resets the grid.
- Step count and population labels update after each step.
