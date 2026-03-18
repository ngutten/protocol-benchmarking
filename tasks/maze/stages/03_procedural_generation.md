# Stage 3: Edge Walls, Doors & Procedural Maze Generation

Extend the maze explorer with procedural maze generation and an edge-based wall
system. Instead of only loading a fixed maze file, the game can now generate
random solvable mazes of configurable size. Walls exist on cell edges (not just
as solid cells), and doors connect rooms. Textures are added in a later stage.

## Requirements

### 1. Maze Generation

Implement a maze generation algorithm (Prim's, recursive backtracker, Kruskal's,
or similar) that produces solvable mazes.

- Generated mazes must have a start position and a goal position
- Must support configurable width and height
- The maze must always be solvable (path from start to goal exists)
- The generator should produce interesting mazes with varied path lengths

### 2. Edge Walls

Support walls on cell edges rather than only solid wall cells.

- A wall can exist between two adjacent open cells (e.g., a wall on the north
  edge of cell (3,4) blocks passage to cell (3,3))
- The internal data structure must represent walls per-edge, not just per-cell
- This is the standard representation for generated mazes

### 3. Doors

Special passable wall segments:

- A door is a wall edge that the player can pass through
- Doors render as visually distinct from solid walls (e.g., wooden door texture,
  different color, door frame shape)
- Doors are opaque — the player cannot see through them until they pass through
- Generated mazes should include some doors

### 4. Minimap Updates

Enhance the minimap for the new features:

- Show doors differently from solid walls on the minimap

### 5. JavaScript API Additions

Add these methods to `window.game`:

```javascript
// Generate a new random maze of the given size
window.game.regenerateMaze(width, height)

// Get wall info for all 4 edges of a cell
// Returns: {n: "wall"|"door"|"open", e: ..., s: ..., w: ...}
window.game.getCellWalls(x, y)
```

All previous `window.game` methods from earlier stages must continue to work.
