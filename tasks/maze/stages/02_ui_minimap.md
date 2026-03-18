# Stage 2: First-Person Rendering & Minimap

Upgrade the maze explorer with a proper first-person 3D perspective view and a
functional minimap. The dungeon logic from Stage 1 (movement, collision, terrain,
goal detection, and the JavaScript API) is already in place. This stage focuses
on the **visual presentation** — immersive 3D rendering and a fog-of-war minimap.

## Requirements

### 1. First-Person 3D Rendering

Render a 3D first-person perspective view of the maze in the `#game-view`
element.

- Walls appear as vertical surfaces receding into the distance
- Floor and ceiling are visible
- Must show at least 3 cells of depth forward
- Make sure the field of view is wide enough that when the player is right up
  against and facing a wall they can still see the floor, ceiling, and any
  adjacent walls to the left and right.
- Simple flat-colored surfaces or lines are acceptable — textures are not
  required in this stage
- Water cells render as a visible floor (blue or distinct color) but the player
  cannot enter them
- Darkness cells render as opaque black — the player cannot see through them
- Goal cells have a distinct visual indicator (glow, special color, icon, etc.)

Any rendering technique is acceptable: raycasting, projected polygons, CSS 3D
transforms, etc.

### 2. Minimap

Display a minimap in `#minimap`, positioned in the upper-left area of the page.

- Shows cells the player has visited (fog of war for unvisited cells)
- Shows the player's current position with a directional indicator
- Walls (`#`) shown distinctly (e.g., dark/filled squares)
- Water (`~`) shown distinctly (e.g., blue)
- Darkness cells (`%`) do NOT appear on the minimap until the player visits them
- Goal (`!`) shown distinctly if within visited/visible area

### 3. Rendering Updates

The 3D view must update in response to player actions:

- Turning changes the view (different walls/corridors visible)
- Moving forward/backward changes the view (perspective shifts)
- The rendering should be responsive and smooth
