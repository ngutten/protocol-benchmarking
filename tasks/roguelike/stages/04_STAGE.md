# Stage 4 — FOV, Lighting, Map Memory

## Goal
Proper line-of-sight using shadowcasting. Light sources with their own FOV.
Tiles remembered after being seen. '?' for heard/recently-seen creatures.

## Deliverables

### FOV System
```cpp
// Recursive shadowcasting (8 octants)
// Returns set of visible positions from origin within max_range
std::unordered_set<Position> compute_fov(
    const TileMap& map,
    Position origin,
    int max_range
);

// The same algorithm is used for:
// 1. Player vision (origin = player_pos, range = vision_range from Perception)
// 2. Light sources (origin = light_pos, range = light_radius)
// 3. Enemy vision (origin = enemy_pos, range = enemy perception)
```

Use symmetric shadowcasting (where if A can see B, B can see A).
This prevents exploitable asymmetries.

### Tile Visibility States
```cpp
enum class Visibility {
    Unseen,     // never viewed; render as blank space
    Remembered, // previously seen; render glyph in dark/dim color
    Visible     // currently in FOV and lit; render normally
};

struct TileMemory {
    // Per-tile: what the player last saw here
    char remembered_glyph;
    bool has_memory = false;
};

struct VisionState {
    std::vector<Visibility> tile_visibility;  // same size as map
    std::vector<TileMemory> tile_memory;      // what player remembers

    // Recomputed each time player moves or light changes
    void update(const TileMap& map, Position player_pos, int vision_range,
                const std::vector<LightSource>& lights);
};

// IMPORTANT: VisionState is per-level.  Each DungeonLevel (Stage 9) stores its
// own tile_visibility and tile_memory.  When the player changes level via
// stairs, the engine switches to the target level's VisionState.  Memory from
// level 0 must NOT bleed into level 1, etc.  On first visit to a new level,
// all tiles start as Unseen.
```

### Lighting System
```cpp
struct LightSource {
    Position pos;
    int radius;
    EntityId source_entity;  // e.g. the ring, a torch on the wall, etc.
    bool carried;            // moves with entity if true
};

// Light computation:
// 1. Compute player FOV (what geometry the player can see)
// 2. For each light source, compute its FOV (what it illuminates)
// 3. A tile is Visible if: it's in player FOV AND (in player's natural sight range
//    OR illuminated by any light source whose FOV reaches it)
//
// This means: the player can see dark areas within their natural range,
// but light sources extend visibility beyond that range (if geometry allows).
// The player must have line-of-sight to the lit tile.
```

A design note: "natural sight range" vs light. The player always has vision within
their Perception-based range (think of it as darkvision / adapted eyes). Light sources
extend the effective range. In dark areas beyond natural range but within a light's
radius, the player can see IF they also have line-of-sight.

### Creature Visibility for Player
```cpp
enum class CreatureVisibility {
    NotKnown,       // player has no information
    Heard,          // detected via sound, not sight — show '?'
    RecentlySeen,   // was visible last turn, now not — show '?' briefly
    Visible         // in FOV and lit — show actual glyph
};

// Sound detection:
// Uses the same stealth-vs-perception formula but at double range:
//   sound_detection_radius = (Perception - target_Stealth) * 2
//   where target_Stealth = target_Mobility * 0.5
// Sound goes through walls (no LOS required), but is reduced by walls:
//   each wall tile on the Bresenham line adds +2 to effective distance.
// If a creature is within sound range but NOT visible, show '?'.
```

### Rendering Rules
| State | Foreground | Background | Glyph shown |
|-------|-----------|------------|-------------|
| Unseen | n/a | n/a | ' ' (space) |
| Remembered | Dark gray | Black | Tile glyph from memory |
| Visible (unlit) | Dim white | Black | Current tile glyph |
| Visible (lit) | Bright white | Black | Current tile glyph |
| Creature Visible | Creature color | Black | Creature glyph |
| Creature Heard | Yellow | Black | '?' |
| Creature RecentlySeen | Dark yellow | Black | '?' |

Use ncurses color pairs:
```cpp
init_pair(1, COLOR_WHITE, COLOR_BLACK);     // normal
init_pair(2, COLOR_YELLOW, COLOR_BLACK);    // heard/recent
init_pair(3, 8, COLOR_BLACK);              // dim (color 8 = dark gray on 256-color terms)
// Fallback for 8-color terminals: use A_DIM attribute
```

### Update to Enemy AI (from Stage 3)
Replace the simplified distance+Bresenham detection with proper FOV:
- Each enemy computes FOV on their turn using the same shadowcasting
- Detection range uses the stealth formula:
  detection_radius = enemy_Perception - player_Stealth
  where player_Stealth = player_effective_Mobility * 0.5
- The enemy can only detect the player within both its FOV AND detection radius
- Enemies are NOT affected by light (they know their own territory)
- This determines `can_see_player` for the AI state machine

## Acceptance Criteria

1. Player can only see tiles within FOV
2. Walls correctly block vision (no seeing through corners)
3. Previously-seen tiles render in dim/dark when out of FOV
4. Unseen tiles render as blank
5. Light sources extend visible area (test: ring of light equipped → larger visible area)
6. Light sources respect geometry (light doesn't go through walls)
7. Creatures outside FOV but within hearing range show as '?'
8. Creatures that were visible last turn but aren't now briefly show as '?'
9. Enemy AI now uses FOV-based detection instead of simple range
10. Symmetric shadowcasting: if player sees enemy, enemy sees player (same range)

## Verification

Automated tests exercise the engine through the JSON-line test harness protocol
defined in `tests/conftest.py`.  The harness builds the project, starts
`test_harness`, and validates behavior by issuing commands and inspecting state.
