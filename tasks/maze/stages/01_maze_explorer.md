# Stage 1: Maze Explorer

Build a first-person grid-based maze exploration game as a web page. The player
navigates a dungeon-style maze from a first-person 3D perspective, exploring
corridors, avoiding water and darkness, and trying to reach the goal. The maze
is loaded from a provided text file (`assets/maze1.txt`). Use WASD keys to move
and turn. A minimap in the corner tracks explored areas.

You can use any web technologies — there are
no restrictions on approach. The result must be servable as static files via
`python3 -m http.server`.

The `assets/` directory is already present in your workspace. Since the game
is served over HTTP (not `file://`), you can load files with
`fetch('assets/maze1.txt')` — no CORS issues arise. Alternatively, you may
embed the maze data directly as a string constant in your JavaScript.

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

### 2. First-Person Rendering

Render a 3D first-person perspective view of the maze in a `#game-view` element.

- Walls appear as vertical surfaces receding into the distance
- Floor and ceiling are visible
- Must show at least 3 cells of depth forward
- Make sure the field of view is wide enough that when the player is right up against and facing a wall they can still see the floor, ceiling, and any adjacent walls to the left and right.
- Simple flat-colored surfaces or lines are acceptable — textures are not
  required in this stage
- Water cells render as a visible floor (blue or distinct color) but the player
  cannot enter them
- Darkness cells render as opaque black — the player cannot see through them
- Goal cells have a distinct visual indicator (glow, special color, icon, etc.)

Any rendering technique is acceptable: raycasting, projected polygons, CSS 3D
transforms, etc.

### 3. Movement

Grid-based movement using keyboard:

- **W** = move forward one cell in the facing direction
- **S** = move backward one cell (opposite to facing direction)
- **A** = turn left 90 degrees
- **D** = turn right 90 degrees

Collision rules:
- Cannot move into wall (`#`) or water (`~`) cells
- Can move into hallway (`.`), darkness (`%`), goal (`!`), and start (`@`) cells

### 4. Minimap

Display a minimap in `#minimap`, positioned in the upper-left area of the page.

- Shows cells the player has visited (fog of war for unvisited cells)
- Shows the player's current position with a directional indicator
- Walls (`#`) shown distinctly (e.g., dark/filled squares)
- Water (`~`) shown distinctly (e.g., blue)
- Darkness cells (`%`) do NOT appear on the minimap until the player visits them
- Goal (`!`) shown distinctly if within visited/visible area

### 5. Goal Detection

When the player moves onto the goal cell (`!`):
- Display a congratulatory message in `#game-message`
- `window.game.isGoalReached()` returns `true`

### 6. JavaScript API

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

### 7. Required DOM Elements

These elements must exist with the specified IDs:

- `#game-view` — the main 3D rendering area (canvas or container)
- `#minimap` — the minimap display
- `#game-message` — area for status messages (can be hidden until needed)
