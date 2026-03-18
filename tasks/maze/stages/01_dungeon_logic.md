# Stage 1: Dungeon Logic

Build the core engine for a first-person grid-based maze exploration game as a
web page. In this stage, focus on the **game logic**: loading the maze, movement,
collision, terrain rules, goal detection, and the JavaScript API. A basic visual
representation in `#game-view` is needed (even a simple top-down or placeholder
view is acceptable) — full 3D rendering comes in a later stage.

You can use any web technologies — there are no restrictions on approach. The
result must be servable as static files via `python3 -m http.server`.

The `assets/` directory is already present in your workspace. Since the game is
served over HTTP (not `file://`), you can load files with
`fetch('assets/maze1.txt')` — no CORS issues arise. Alternatively, you may embed
the maze data directly as a string constant in your JavaScript.

## Requirements

### 1. Maze Loading

Parse `assets/maze1.txt` to build the maze grid. The file uses these characters:

- `#` = solid wall (blocks movement and vision)
- `.` = open hallway (traversable, visible)
- `%` = darkness (traversable, renders opaque black, blocks vision)
- `~` = water (impassable, but visible — player can see over it)
- `!` = goal (traversable, distinct visual, triggers reward)
- `@` = player start position (treat as hallway after spawning)

The maze is rectangular. Row 0 is the top of the file, column 0 is the left.

### 2. Movement

Grid-based movement using keyboard:

- **W** = move forward one cell in the facing direction
- **S** = move backward one cell (opposite to facing direction)
- **A** = turn left 90 degrees
- **D** = turn right 90 degrees

Collision rules:
- Cannot move into wall (`#`) or water (`~`) cells
- Can move into hallway (`.`), darkness (`%`), goal (`!`), and start (`@`) cells

### 3. Goal Detection

When the player moves onto the goal cell (`!`):
- Display a congratulatory message in `#game-message`
- `window.game.isGoalReached()` returns `true`

### 4. JavaScript API

Expose `window.game` with these methods:

```javascript
window.game = {
    getPlayerPosition()   // → {x: int, y: int}  (column, row)
    getPlayerDirection()  // → "N" | "E" | "S" | "W"
    isGoalReached()       // → boolean
    getVisitedCells()     // → [{x, y}, ...]
    getMazeCell(x, y)     // → "#" | "." | "%" | "~" | "!"
    getMazeWidth()        // → int  (number of columns)
    getMazeHeight()       // → int  (number of rows)
}
```

### 5. Required DOM Elements

These elements must exist with the specified IDs:

- `#game-view` — the main rendering area (canvas or container); must have
  non-zero dimensions. A basic visual is sufficient for this stage.
- `#minimap` — the minimap display area (can be a placeholder in this stage)
- `#game-message` — area for status messages (can be hidden until needed)
