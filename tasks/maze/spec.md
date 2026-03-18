# Maze Explorer: First-Person Web Maze Game

## Overview

Web-based first-person maze exploration game. The player navigates a grid-based
maze from a first-person perspective using WASD controls. The game renders a 3D
view of the maze, includes a minimap, supports special terrain types (walls,
water, darkness), and provides goal detection.

## Entry Point

- Main file: open-ended (the AI chooses HTML/JS/CSS structure)
- Must be servable as static files via any HTTP server
- Main page accessible at the root as `index.html`
- Engine cmd: `cd <workspace> && python3 -m http.server 8000`

## Assets

The `assets/` directory is present in the workspace alongside `index.html`.
Since the game is served via `python3 -m http.server` (HTTP, not `file://`),
relative fetches like `fetch('assets/maze1.txt')` work without CORS issues.
Alternatively, the maze data can be embedded directly as a string constant.

## Maze File Format

The maze is defined in a text file (`assets/maze1.txt`) using these characters:

| Char | Meaning | Traversable | Visible Through |
|------|---------|-------------|-----------------|
| `#`  | Wall    | No          | No              |
| `.`  | Hallway | Yes         | Yes             |
| `%`  | Darkness| Yes         | No (opaque black) |
| `~`  | Water   | No          | Yes (see over)  |
| `!`  | Goal    | Yes         | Yes             |
| `@`  | Start   | Yes (spawn) | Yes             |

Coordinate system: the maze file is read row by row, top to bottom. Row 0 is
the top. Column 0 is the left. Position (x, y) means column x, row y.

## Game Mechanics

- **Grid-based movement**: W = move forward, S = move backward, A = turn left,
  D = turn right
- Each move is exactly one cell; each turn is exactly 90 degrees
- Player cannot move through walls (`#`) or water (`~`)
- Player CAN move through hallways (`.`), darkness (`%`), and the goal (`!`)
- The start cell (`@`) is treated as a hallway after spawning
- Reaching `!` triggers a goal/reward state

## Rendering Requirements

- First-person 3D perspective view of the maze
- Must render at least 3 cells of depth forward
- Walls rendered as vertical surfaces with perspective foreshortening
- Floor and ceiling visible
- Water (`~`) renders as a visible floor surface (player sees over it) but
  blocks movement
- Darkness (`%`) renders as opaque black; player cannot see through it
- Goal (`!`) has a distinct visual feature (glow, color, icon, etc.)

## Minimap

- Displayed in the upper-left corner of the page
- Shows cells the player has visited (fog of war)
- Shows the player's current position and facing direction
- Darkness cells (`%`) do NOT appear on the minimap until the player enters them
- Water (`~`) and walls (`#`) shown distinctly from hallways
- Goal shown distinctly if visible

## JavaScript API

The game must expose the following on `window.game` for testing:

```javascript
window.game = {
    getPlayerPosition()   // → {x: int, y: int}
    getPlayerDirection()  // → "N" | "E" | "S" | "W"
    isGoalReached()       // → boolean
    getVisitedCells()     // → [{x, y}, ...]
    getMazeCell(x, y)     // → "#" | "." | "%" | "~" | "!"
    getMazeWidth()        // → int
    getMazeHeight()       // → int
}
```

Direction convention:
- **N** = towards row 0 (up in the maze file)
- **S** = towards higher rows (down in the maze file)
- **E** = towards higher columns (right)
- **W** = towards lower columns (left)

## Required DOM Elements

| Element      | Selector        | Purpose                              |
|--------------|-----------------|--------------------------------------|
| Game view    | `#game-view`    | Main 3D rendering area (canvas/div)  |
| Minimap      | `#minimap`      | Minimap display area                 |
| Message area | `#game-message` | Status messages (goal found, etc.)   |
