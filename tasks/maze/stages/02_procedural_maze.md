# Stage 2: Procedural Maze Generation & Texture Rendering

Extend the maze explorer with procedural maze generation and rich texture
support. Instead of loading a fixed maze file, the game can now generate random
solvable mazes of configurable size. Walls exist on cell edges (not just as
solid cells), doors connect rooms, and all surfaces display high-resolution
textures for an immersive dungeon experience.

The provided texture PNG files in `assets/textures/` must be loaded and applied
to the appropriate surfaces. Do not overwrite this or generate your own variants!

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

### 4. Textures

Apply the provided 1024x1024 PNG texture files to rendered surfaces:

**Wall textures** (applied to wall surfaces):
- `assets/textures/wall_stone.png`
- `assets/textures/wall_brick.png`
- `assets/textures/wall_metal.png`

**Floor textures** (applied to floor surfaces):
- `assets/textures/floor_wood.png`
- `assets/textures/floor_tile.png`
- `assets/textures/floor_carpet.png`

**Water floor texture** (applied to water `~` tiles):
- `assets/textures/floor_water.png`

**Ceiling textures** (applied to ceiling surfaces):
- `assets/textures/ceiling_plaster.png`
- `assets/textures/ceiling_cave.png`

Different areas of the maze should use different textures to create visual
variety (e.g., stone walls in one section, brick walls in another).

### 5. Minimap Updates

Enhance the minimap for the new features:

- Show floor texture colors or a visual gist on the minimap
- Show wall texture colors or distinct markings on minimap edges
- Show doors differently from solid walls on the minimap

### 6. JavaScript API Additions

Add these methods to `window.game`:

```javascript
// Generate a new random maze of the given size
window.game.regenerateMaze(width, height)

// Get wall info for all 4 edges of a cell
// Returns: {n: "wall"|"door"|"open", e: ..., s: ..., w: ...}
window.game.getCellWalls(x, y)

// Get texture names assigned to a cell's floor and ceiling
// Returns: {floor: string, ceiling: string}
window.game.getCellTextures(x, y)
```

All previous `window.game` methods from Stage 1 must continue to work.
