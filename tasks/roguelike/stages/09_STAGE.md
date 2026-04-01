# Stage 9 — Procedural Dungeon Generation

## Goal
Modular dungeon generator producing playable multi-level dungeons.
Persistent levels with staircases connecting them. Edge exits for overworld.

## Deliverables

### Generator Architecture
```cpp
// The generator is a pipeline of phases.
// Each phase takes the current map state and modifies it.

class MapGenPhase {
public:
    virtual ~MapGenPhase() = default;
    virtual void apply(TileMap& map, std::mt19937& rng) = 0;
    virtual std::string name() const = 0;
};

// The pipeline
struct MapGenConfig {
    int width = 80;
    int height = 40;
    std::vector<std::unique_ptr<MapGenPhase>> phases;
};

TileMap generate_map(MapGenConfig& config, std::mt19937& rng);
```

### Phase 1: Corridor/Tunnel Generator
Several options; implement at least one, make it swappable:

**Option A: BSP (Binary Space Partition)**
1. Recursively split the map into rectangular regions
2. Each leaf region gets a room
3. Connect sibling regions with corridors
4. Good for traditional dungeon layouts

**Option B: Drunk Walk / Random Walk**
1. Start from center, carve corridors by random walking
2. Bias toward unexplored areas
3. More organic/cave-like

**Option C: Cellular Automata**
1. Random fill (~45% walls)
2. Iterate: cell becomes wall if 5+ neighbors are walls, floor if <4
3. Good for caverns

Implement BSP as the default; the interface allows swapping in alternatives.

### Phase 2: Room Placer
```cpp
struct RoomDef {
    int min_width, max_width;
    int min_height, max_height;
};

class RoomPlacerPhase : public MapGenPhase {
    int num_rooms;
    RoomDef room_size;
    int max_placement_attempts;  // prevent infinite loops on tight maps
public:
    void apply(TileMap& map, std::mt19937& rng) override;
    // Places rooms by carving floor tiles into the existing map
    // Rooms must not overlap each other (or must overlap minimally)
    // Corridors connect rooms to nearest neighbor or to existing corridors
};
```

### Phase 3: Template Injector
```cpp
struct RoomTemplate {
    std::string name;
    int width, height;
    std::vector<char> layout;  // row-major, using map glyphs
    // Special characters:
    // '.' = floor, '#' = wall, '<' = stairs up, '>' = stairs down
    // 'D' = door (future), 'T' = trap (future)
    // '1'-'9' = spawn points (for enemies/items)
    // ' ' = don't modify (preserve underlying map)

    // Metadata
    int min_depth = 0;      // earliest dungeon level this can appear
    int max_depth = -1;     // -1 = no limit
    bool unique = false;    // only place once across all levels
    bool required = false;  // must appear on applicable levels
};

class TemplateInjectorPhase : public MapGenPhase {
    std::vector<RoomTemplate> templates;
    int max_templates_per_level;
public:
    void apply(TileMap& map, std::mt19937& rng) override;
    // Find a suitable location (enough space, not overlapping critical features)
    // Stamp the template into the map
    // Connect to existing corridors if isolated
};
```

### Phase 4: Staircase Placer
```cpp
class StaircasePlacerPhase : public MapGenPhase {
public:
    void apply(TileMap& map, std::mt19937& rng) override;
    // Place one stairs-up and one stairs-down
    // Stairs should be reasonably far apart (at least half the map diagonal)
    // Stairs-up on level 0 = entrance
    // Stairs must be reachable from each other (path exists)
};
```

### Phase 5: Entity Populator
```cpp
struct PopulationConfig {
    // Difficulty scaling
    int dungeon_level;
    float enemy_density;      // enemies per 100 floor tiles
    float item_density;       // items per 100 floor tiles

    // Creature pools per depth
    struct SpawnEntry {
        CreatureTemplate creature;
        int min_depth, max_depth;
        float weight;         // relative probability
    };
    std::vector<SpawnEntry> creature_pool;

    // Item pools per depth
    struct ItemSpawnEntry {
        std::string item_template_name;
        int min_depth, max_depth;
        float weight;
    };
    std::vector<ItemSpawnEntry> item_pool;
};

// Required item pool entries (all items must be encounterable via normal play):
//
// | Item                      | min_depth | max_depth | weight |
// |---------------------------|-----------|-----------|--------|
// | healing_potion            | 0         | -1        | 3.0    |
// | buff_potion               | 1         | -1        | 1.5    |
// | iron_sword                | 0         | 3         | 1.0    |
// | shortbow                  | 1         | 5         | 0.8    |
// | iron_helmet               | 0         | 4         | 1.0    |
// | leather_armor             | 0         | 3         | 1.0    |
// | leather_gloves            | 0         | 4         | 1.2    |
// | ring_of_light             | 2         | -1        | 0.5    |
// | stealth_cloak             | 3         | -1        | 0.3    |
// | speed_boots               | 2         | -1        | 0.5    |
// | leather_pouch             | 0         | -1        | 1.0    |
// | gold_ring                 | 0         | -1        | 1.5    |
// | skillbook_leaping_strike  | 1         | -1        | 0.4    |
// | skillbook_magic_missile   | 2         | -1        | 0.4    |
// | skillbook_sleep           | 2         | -1        | 0.3    |
//
// This ensures players can organically find weapons, armor, potions,
// containers, and skill books by exploring the dungeon — not just via
// test-harness commands.

// Required creature pool entries:
//
// | Creature  | min_depth | max_depth | weight |
// |-----------|-----------|-----------|--------|
// | goblin    | 0         | 4         | 3.0    |
// | skeleton  | 1         | -1        | 2.0    |
// | ogre      | 3         | -1        | 0.5    |  (Stage 12: 2×2)
//
// The ogre entry uses the multi-tile body (2×2) from Stage 12.  Before
// Stage 12, skip it (or guard behind a stage check).  Once Stage 12 is
// implemented, ogres must actually appear in the dungeon on depth ≥ 3.

class PopulatorPhase : public MapGenPhase {
    PopulationConfig config;
public:
    void apply(TileMap& map, std::mt19937& rng) override;
    // Determine number of enemies/items from density * floor tile count
    // Select from pools weighted by depth
    // Place on random floor tiles, avoiding stairs and player spawn
    // Store spawn data for engine to instantiate entities
};
```

### Level Management
```cpp
struct DungeonLevel {
    int depth;
    TileMap map;
    std::vector<EntityId> entities;   // creatures on this level
    std::vector<EntityId> items;      // items on ground
    std::vector<LightSource> lights;

    // Staircase connections
    struct StairConnection {
        Position stair_pos;       // position on this level
        int target_depth;         // which level it connects to
        Position target_pos;      // position on target level
    };
    std::vector<StairConnection> stairs;

    // Edge exits (for surface/overworld)
    struct EdgeExit {
        Position exit_pos;
        std::string target_area;  // name/id of connected area
        Position entry_pos;       // where player appears in target
    };
    std::vector<EdgeExit> edge_exits;
};

class DungeonManager {
    std::unordered_map<int, DungeonLevel> levels;  // depth → level
    int current_depth = 0;
public:
    DungeonLevel& current_level();
    DungeonLevel& get_or_generate(int depth, std::mt19937& rng);

    // Staircase traversal
    // Returns new player position on target level
    Position use_stairs(Position stair_pos);

    // Freeze entities on old level (they stop taking turns)
    void freeze_level(int depth);
    // Thaw entities on new level
    void thaw_level(int depth);
};
```

### Default Generator Pipeline
```cpp
MapGenConfig default_dungeon_config(int depth) {
    MapGenConfig config;
    config.width = 80;
    config.height = 40;
    config.phases.push_back(std::make_unique<BSPPhase>(
        /*min_room=*/5, /*max_room=*/12, /*min_split=*/15));
    config.phases.push_back(std::make_unique<RoomPlacerPhase>(
        /*num_rooms=*/3, RoomDef{8, 15, 6, 10}, /*attempts=*/50));
    config.phases.push_back(std::make_unique<TemplateInjectorPhase>(
        get_templates_for_depth(depth), /*max=*/2));
    config.phases.push_back(std::make_unique<StaircasePlacerPhase>());
    config.phases.push_back(std::make_unique<PopulatorPhase>(
        get_population_config(depth)));
    return config;
}
```

### Example Template: Treasure Room
```
#####
#...#
#.$.#      $ = treasure chest spawn point
#...#
##D##      D = door (or just floor for now)
```

### Example Template: Ambush Corridor
```
.........
#1#.#2#.#     1,2 = enemy spawn points
.........
```

### Level-Specific Tile Memory

Each DungeonLevel stores its own VisionState (tile_visibility and tile_memory
from Stage 4).  When the player changes levels:
1. The current level's VisionState is preserved (frozen with the level).
2. The target level's VisionState is restored (or initialized to all-Unseen
   if this is the first visit).
3. FOV is recomputed for the new level.

This means: remembered tiles from level 0 do NOT appear on level 1.  Each
level's exploration progress is tracked independently.  The `state` response
fields `visible_tiles` and `remembered_tiles` always reflect the CURRENT
level only.

### State Updates
The `state` response gains these fields:
- `dungeon_level`: current depth (int)
- `levels_visited`: number of distinct levels generated (int)
- `map.stairs_up`: `{x, y}` position of the up staircase on the current level
- `map.stairs_down`: `{x, y}` position of the down staircase on the current level

### Player Spawn
On New Game: player spawns at stairs-up on level 0.
On descending: player appears at stairs-up on the new level.
On ascending: player appears at stairs-down on the level above.

### Staircase Interaction Flow

**Player presses '>' (descend):**
1. Check: is the player standing on a StairsDown tile? If not: "There are no stairs going down here."
2. End the current turn (any remaining movement is lost).
3. Freeze current level: enemies stop acting, effects stop ticking.
4. Look up the StairConnection to find the target depth and position.
5. If the target level has been visited: load it from the DungeonManager.
   If not: generate it using `get_or_generate(target_depth, rng)`.
6. Move player to the target position (stairs-up on the new level).
7. Thaw the new level: enemies and effects become active again.
8. Recompute FOV and lighting for the new level.
9. Log message: "You descend to level N."
10. The new level's enemy phase does NOT trigger immediately — the player
    gets a fresh movement bar to orient themselves.

**Player presses '<' (ascend):**
1. Check: is the player standing on a StairsUp tile? If not: "There are no stairs going up here."
2. On level 0, stairs-up is the dungeon entrance. Ascending here could either:
   - Show a prompt: "Leave the dungeon? (y/n)" → return to surface/main menu
   - Or simply: "The way is barred." (if we don't have a surface level)
   - Implementation choice; spec both behaviors, pick one.
3. Otherwise: same flow as descending but in reverse — move to stairs-down
   on the level above.
4. Log message: "You ascend to level N."

**Edge exits (level 0 only):**
Player walks into an edge exit tile:
1. Check the EdgeExit data for the target area and entry position.
2. Same freeze/thaw/generate flow as staircases.
3. For the benchmark, edge exits can be left as "The way leads to the surface.
   You decide to stay in the dungeon." (i.e., non-functional but acknowledged).

**Movement cost:**
Using stairs consumes no movement points — it simply ends the turn.
This prevents the player from descending and immediately being attacked
before they can see the new level.

## Acceptance Criteria

1. Generated maps are playable: connected, navigable, have stairs
2. BSP generates rooms connected by corridors
3. Room placer adds additional rooms without breaking connectivity
4. Templates can be injected into the map
5. Staircases connect levels in both directions
6. Using stairs generates new level (if not visited) or loads existing
7. Entities on inactive levels don't take turns
8. Multiple generator phases compose correctly
9. Different seeds produce different maps
10. Same seed produces identical map
11. Population density scales with depth
12. Edge exits exist on level 0 (surface)
13. '>' on stairs-down tile descends; error message if not on stairs
14. '<' on stairs-up tile ascends; error message if not on stairs
15. Player gets a fresh movement bar after using stairs (no ambush on arrival)
16. Using stairs ends the current turn (remaining movement lost)
17. Tile memory is level-specific: descending to a new level starts with all tiles Unseen
18. Returning to a previously visited level restores that level's tile memory
19. Item pool includes all defined items at appropriate depths (potions, weapons, armor, skill books, containers)
20. Creature pool includes goblins, skeletons, and ogres (2×2, depth ≥ 3) at appropriate depths

## Verification

Automated tests exercise the engine through the JSON-line test harness protocol
defined in `tests/conftest.py`.  The harness builds the project, starts
`test_harness`, and validates behavior by issuing commands and inspecting state.
