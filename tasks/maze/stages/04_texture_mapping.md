# Stage 4: Texture Mapping

Add high-resolution texture support to the maze renderer. The provided texture
PNG files in `assets/textures/` must be loaded and applied to the appropriate
surfaces. Do not overwrite these or generate your own variants!

## Requirements

### 1. Textures

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

### 2. Minimap Updates

Enhance the minimap for textures:

- Show floor texture colors or a visual gist on the minimap
- Show wall texture colors or distinct markings on minimap edges

### 3. JavaScript API Additions

Add this method to `window.game`:

```javascript
// Get texture names assigned to a cell's floor and ceiling
// Returns: {floor: string, ceiling: string}
window.game.getCellTextures(x, y)
```

All previous `window.game` methods from earlier stages must continue to work.
