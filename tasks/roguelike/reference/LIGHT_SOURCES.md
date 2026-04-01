# Light Source Specification

## Light Source Types

There are three categories of light source, distinguished by how their
position updates. The FOV/illumination computation is identical for all three.

### 1. Carried Light Sources
A light attached to an entity (player or creature). Moves with the entity.

```cpp
struct LightSource {
    EntityId id;            // unique identifier
    Position pos;           // current position (updated each tick)
    int radius;
    EntityId owner;         // entity carrying it; 0 = none (fixed)
    EntityId source_item;   // the item producing the light (e.g., Ring of Light)
    bool active = true;

    bool is_carried() const { return owner != 0; }
    bool is_fixed() const { return owner == 0; }
};
```

**Lifecycle:**
- Created when a light-producing item is equipped (Ring of Light `on_equip`)
- Position updated to owner's position at the start of each turn
  (before FOV computation)
- Destroyed when the item is unequipped (`on_deequip`), or when the
  owner dies and the item is dropped (becomes fixed at drop position)

**Example:** Ring of Light
```
on_equip: create LightSource{radius=8, owner=player_id, source_item=ring_id}
on_deequip: destroy LightSource with source_item==ring_id
```

### 2. Fixed Light Sources (Map Features)
Lights that are part of the dungeon — wall torches, glowing crystals,
lava pools, magical runes, etc. These never move.

```cpp
// Fixed lights are stored per-level in the DungeonLevel struct.
// They are placed during map generation and persist with the level.
```

**Lifecycle:**
- Created during map generation (by a MapGenPhase, or by a RoomTemplate)
- Persist with the level (saved/loaded with level data)
- Can be destroyed by game events (e.g., extinguishing a torch)
- Never move

**Map generation integration:**
```cpp
// In a room template, 'L' = light source placement
// Template definition includes light radius
struct TemplateLightDef {
    int local_x, local_y;   // position within template
    int radius;
};

// The PopulatorPhase can also scatter random torches along corridors
```

### 3. Dropped Light Sources
A carried light that has been dropped. This is really just a transition:
when a carried light's item is dropped to the ground, the LightSource
changes from carried to fixed at the drop position.

```cpp
// When an item that is a light source is dropped:
void handle_light_item_dropped(EntityId item_id, Position drop_pos) {
    auto* light = find_light_by_source_item(item_id);
    if (light) {
        light->owner = 0;          // no longer carried
        light->pos = drop_pos;     // fix at drop position
    }
}

// When picked up again:
void handle_light_item_picked_up(EntityId item_id, EntityId new_owner) {
    auto* light = find_light_by_source_item(item_id);
    if (light) {
        light->owner = new_owner;
        // Position will be updated to owner's pos on next turn
    }
}
```

## Illumination Computation

Each tick, after entity positions are updated and before rendering:

```
1. Collect all active LightSources on the current level
2. Update carried light positions to their owner's current position
3. Compute player FOV (shadowcasting from player_pos, range = vision_range)
4. For each light source:
   a. Compute light FOV (shadowcasting from light_pos, range = light_radius)
   b. Store the set of illuminated tiles
5. A tile is Visible if:
   - It is in the player's FOV geometry (player has line of sight to it)
   AND
   - It is within the player's natural vision range
     OR it is illuminated by any light source
6. A tile is Remembered if it was previously Visible but is not currently
7. A tile is Unseen if it has never been Visible
```

### Key design point: player FOV vs illumination

The player's FOV (line-of-sight geometry) is computed at a generous range
(enough to cover the largest possible light radius). This tells us what
the player *could* see if it were lit. Then we intersect with illumination
to determine what they *actually* see.

```cpp
void update_visibility(VisionState& vis, const TileMap& map,
                       Position player_pos, int vision_range,
                       const std::vector<LightSource>& lights) {
    // 1. Compute raw LOS geometry (large range to cover all possible lights)
    int max_light_radius = 0;
    for (auto& l : lights) max_light_radius = std::max(max_light_radius, l.radius);
    int fov_range = std::max(vision_range, max_light_radius + 5);

    auto player_los = compute_fov(map, player_pos, fov_range);

    // 2. Compute illuminated tiles
    std::unordered_set<Position> illuminated;
    for (auto& light : lights) {
        if (!light.active) continue;
        auto light_fov = compute_fov(map, light.pos, light.radius);
        illuminated.insert(light_fov.begin(), light_fov.end());
    }

    // 3. Determine visibility
    for (auto& pos : player_los) {
        int dist = distance(player_pos, pos);
        bool in_natural_range = (dist <= vision_range);
        bool is_lit = illuminated.count(pos) > 0;

        if (in_natural_range || is_lit) {
            vis.set(pos, Visibility::Visible);
            vis.remember(pos, map.at(pos.x, pos.y).glyph);
        }
        // If in LOS but beyond natural range and not lit:
        // leave as Remembered or Unseen (player can't see in the dark)
    }
}
```

### Darkness and "natural vision"

The player's `vision_range` (from Perception) represents how far they can
see in complete darkness — ambient/adapted vision. A well-lit room extends
this. A player with Perception 10 and vision_range 7 can see 7 tiles in
any direction in the dark. With a Ring of Light (radius 8), they can see
up to 8 tiles in lit directions, plus the 7-tile dark vision in all
other directions.

### Enemy vision and light

Enemies use the same FOV algorithm but are NOT affected by light for
detection purposes. They "know their territory" and can see within their
full perception range regardless of lighting. This is a gameplay simplification
that prevents the player from exploiting darkness trivially.

However, enemies DO use light sources for one thing: creatures with the
"light-sensitive" flag (future feature) could have reduced perception
in lit areas.

## Light Sources in Rendering

| Condition | Appearance |
|-----------|------------|
| Tile in natural vision range, no light | Normal colors (dim white) |
| Tile in light source range | Bright/warm colors (bright white or yellow tint) |
| Tile beyond natural range, in light | Visible but slightly different tint (shows it's lit from afar) |
| Tile in FOV geometry but beyond range and not lit | NOT visible (dark) |
| Tile not in FOV geometry | Remembered (dark gray) or Unseen (blank) |

Color pairs for light rendering:
```cpp
init_pair(TILE_DARK, COLOR_WHITE, COLOR_BLACK);       // natural vision, no light
init_pair(TILE_LIT, COLOR_YELLOW, COLOR_BLACK);        // directly lit
init_pair(TILE_DIM_MEMORY, 8, COLOR_BLACK);            // remembered tile (dark gray)
// 256-color terminals can use warmer tones for lit areas
```

## Performance Considerations

FOV computation for each light source is O(n) where n is tiles in range.
With many light sources, this could get expensive. Mitigations:
- Only recompute light FOV when the light source moves (carried) or
  when the map changes (rare)
- Cache light FOV for fixed sources (compute once, store result)
- For carried sources, recompute each turn (they move)
- Skip lights that are entirely outside the player's extended FOV
  (their illumination can't affect what the player sees)

```cpp
struct CachedLightFOV {
    Position computed_at;
    std::unordered_set<Position> tiles;
    bool dirty = true;

    void invalidate() { dirty = true; }
    bool needs_recompute(Position current_pos) const {
        return dirty || current_pos != computed_at;
    }
};
```
