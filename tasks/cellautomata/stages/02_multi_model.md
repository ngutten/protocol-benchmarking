# Stage 2: Multi-Model Support

We want to add multiple cellular automata to the UI, accessible via a dropdown menu.
In particular, you should make a mode for Falling Sand and for Langton's Ant.

The Falling Sand model should work as follows: We have grains (state=1) which fall downwards
if unsupported from below. If the cell below a grain has state=1, then we look to the left
and right and count how far down we must go until we hit a boundary or a state=1 cell in each
direction, with a distance of zero implying adjacency at the same height, a distance of one being 
just below that, and so on. If those distances are both 2 or less (e.g. a 45 degree angle=2, 
a flat surface=1, or supported by an adjacent grain in that direction=0) then the grain stays 
in place. Otherwise, the grain moves horizontally either to the left or right based on which 
distance is greater. There is a special case where the distances are equal, in which case the 
grain should not fall. Another special case is if two grains would enter the same cell 
(e.g. from left and right) then one of them moves below (which should be empty space because distance>2). 
All movements are computed from the grid state at the start of the iteration and occur simultaneously. 

As before, make sure you maintain a library API as well, according to the following:

## Goal

Extend `cellautomata.py` to support Falling Sand and Langton's Ant models,
add model-specific API methods, and add a model selection dropdown to the GUI.

## Requirements

### New Models

The `model` parameter in `Simulation.__init__` now accepts `"conway"`, `"sandpile"`,
or `"langton"`. Unknown model names raise `ValueError`.

### Falling Sand (model="sandpile")

**Grid**: (0,1) values = 1 is a grain, 0 is empty space.

**Orientation**: Gravity pulls downward — toward row index `height-1`. The bottom
row (`y = height-1`) acts as the floor; grains cannot fall below it. Grains never
move upward (against gravity).

**Boundary behavior**:
- `"constant"`: off-grid cells are treated as height 0 for difference
  calculations. A grain that moves off-grid is lost.
- `"periodic"`: lateral (left/right) neighbors wrap to the opposite edge.
  The bottom row is still the floor. All grains are conserved.

**Methods**:
- `step(n=1)`: perform `n` simultaneous sweeps
- `topple() -> int`: repeat sweeps until stable, return total individual
  grain-move events across all sweeps
- `is_stable() -> bool`: return `True` if no grain would move in the next step

**Errors**: calling `topple()` or `is_stable()` on a non-sandpile model raises
`TypeError`.

### Langton's Ant (model="langton")

**Grid**: Binary (0 or 1), plus an ant state: position (x, y) and direction
(N/E/S/W).

**Step rule**:
1. At current cell: if 0, turn right 90 degrees; if 1, turn left 90 degrees
2. Flip the current cell (0 <-> 1)
3. Move forward one cell in the current direction

**Direction mapping** (compass): N = up (y-1), E = right (x+1), S = down (y+1),
W = left (x-1).

**Default ant**: center of grid `(width//2, height//2)`, facing N.

**Boundary behavior**:
- `"periodic"`: ant wraps to opposite edge
- `"constant"`: raises `StopIteration` if ant would move off grid

**Methods**:
- `get_ant() -> dict`: return `{"x": int, "y": int, "direction": str}`
- `set_ant(x, y, direction="N")`: set ant position and direction

**Errors**: calling `get_ant()` or `set_ant()` on a non-langton model raises
`TypeError`.

### Cross-Model Error Handling

- `topple()` / `is_stable()` on non-sandpile: `TypeError`
- `get_ant()` / `set_ant()` on non-langton: `TypeError`

## GUI Changes

### Model Selection Dropdown

Add a `QComboBox` with `objectName="combo_model"` containing three items:
`"conway"`, `"sandpile"`, `"langton"`.

**Behavior**: when the user selects a different model, create a new `Simulation`
with that model and reset the display. The grid dimensions and boundary setting
should be preserved.

### Labels

`lbl_step_count` and `lbl_population` continue to update for all models.
For falling sand (sandpile), population = sum of all cell values. For langton,
population = count of cells equal to 1.
