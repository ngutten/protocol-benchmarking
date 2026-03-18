# Stage 1: Conway's Game of Life

Write a Python program using PySide6 called `cellautomata.py` to simulate Conway's Game of Life. The user
should see a 64x64 grid of cells 4 pixels by 4 pixels each, should be able to click on cells to flip their
state, press the 'Start' button to run the simulation continuously, the 'Stop' button to halt the simulation,
and the 'Reset' button to reset the state to all zeroes. Make sure the UI is reasonable and usable for these
parameters. The grid should have periodic boundaries.

Behind the scenes, you'll implement the simulation as library functions which could be called by some other
piece of Python code. The details of the library API are as follows:

## Goal

Implement the core `Simulation` class with Conway's Game of Life and a basic
PySide6 GUI. This stage establishes the library API, grid operations, boundary
conditions, and the main window.

## Requirements

### Simulation Class

Create `cellautomata.py` with a `Simulation` class supporting:

```python
class Simulation:
    def __init__(self, width=256, height=256, model="conway", boundary="periodic")
```

**Constructor parameters:**
- `width`, `height`: grid dimensions (positive integers)
- `model`: only `"conway"` required for this stage (raise `ValueError` for unknown)
- `boundary`: `"periodic"` (wrapping) or `"constant"` (dead cells outside)

### Grid Operations

- `get_cell(x, y) -> int`: return cell value; raise `IndexError` if out of bounds
- `set_cell(x, y, value: int)`: set cell value; raise `IndexError` if out of bounds
- `toggle_cell(x, y)`: flip between 0 and 1
- `clear()`: set all cells to 0 and reset step count to 0
- `get_grid() -> list[list[int]]`: return a deep copy, indexed as `[row][col]`
- `set_grid(grid: list[list[int]])`: replace grid; raise `ValueError` if dimensions mismatch

### Conway's Game of Life Rules

- Binary grid: cells are 0 (dead) or 1 (alive)
- B3/S23 rule with Moore neighborhood (8 neighbors)
- Synchronous update: compute next state from current state simultaneously
- **Periodic boundary**: cells on edges wrap to opposite side
- **Constant boundary**: cells outside grid are treated as 0

### Simulation Control

- `step(n=1)`: advance n generations; raise `ValueError` if n < 1
- `get_step_count() -> int`: total steps taken since creation or last `clear()`

### Analysis

- `count_alive() -> int`: count of cells with value > 0
- `get_population_history() -> list[int]`: list of `count_alive()` values recorded
  after each `step()` call (each individual step in a multi-step call)

### Pattern Loading

- `load_pattern(pattern, offset_x=0, offset_y=0)`: set cells at given (x, y)
  coordinates to 1, with optional offset. On periodic grids, coordinates wrap.

### Read-only Properties

- `width`, `height`, `model`, `boundary`

## GUI

### Window: `CellAutomataWindow`

A `QMainWindow` subclass with the following widgets (identified by `objectName`):

| Widget           | objectName       | Type        | Behavior                    |
|------------------|------------------|-------------|-----------------------------|
| Start button     | `btn_start`      | QPushButton | Start auto-stepping timer   |
| Stop button      | `btn_stop`       | QPushButton | Stop auto-stepping timer    |
| Reset button     | `btn_reset`      | QPushButton | Call `clear()`, update view |
| Grid display     | `grid_view`      | QWidget     | Visual grid, click toggles  |
| Step count label | `lbl_step_count` | QLabel      | Shows current step count    |
| Population label | `lbl_population` | QLabel      | Shows current alive count   |

### Entry Point

When run as `python3 cellautomata.py`, create a `QApplication`, show
`CellAutomataWindow`, and enter the event loop. Default simulation: 256x256
periodic Conway.
