# Stage 3 — Abilities, Ranged Combat & Targeting, Procedural Generation

## Goal
Ability system is live. Player can learn, bind, forget, and use abilities.
Three test abilities implemented: Leaping Strike, Magic Missile, Sleep.
Two-keypress activation: 'a' then binding key.

## Deliverables

### Ability Data Model
```cpp
enum class AbilityType { Martial, Magical };

enum class TargetingMode {
    Self,           // no targeting needed
    SingleTarget,   // select one enemy
    Direction,      // choose a direction (8-way)
    AreaOfEffect,   // select center point, affects radius
    Line            // select direction, affects line
};

struct AbilityData {
    std::string internal_name;
    std::string display_name;
    std::string description;
    AbilityType type;
    int slot_cost;              // how many Lore-based slots this consumes
    int mp_cost;                // 0 for martial abilities
    TargetingMode targeting;
    int range;                  // for ranged targeting modes
    float aoe_base_radius;     // base radius; actual = base + f(Technique)

    // The actual effect — registered callback
    std::string effect_name;    // key into ability effect registry
};

using AbilityEffect = std::function<void(
    GameEngine& engine,
    EntityId user,
    Position target,            // target position (for targeted abilities)
    std::vector<EntityId> affected  // entities in AoE (precomputed)
)>;

struct AbilitySet {
    std::vector<AbilityData> known_abilities;
    std::unordered_map<char, int> bindings;  // key → index into known_abilities
    int total_slots_used() const;
    int max_slots;  // = ability_slots() from Lore

    bool can_learn(const AbilityData& ability) const;
    void learn(AbilityData ability);
    void forget(int index);
    void bind(int index, char key);
    void unbind(char key);
};
```

### Two-Keypress Activation Flow
1. Player presses 'a' → enter ability mode
2. Bottom bar shows: "Use ability: [1] Leaping Strike  [2] Magic Missile  [3] Sleep  [Esc] cancel"
3. Player presses bound key (e.g., '1')
4. If ability requires targeting: enter targeting mode (reuse/extend from Stage 8 spec)
5. If ability is Self-targeted: execute immediately
6. Ability consumes MP (for magical) and consumes remaining movement bar
7. If insufficient MP: "Not enough magic power." Cancel.
8. If no valid targets in range: "No valid targets." Cancel.

### Ability Screen UI (opened with 'A' — capital A, shift+a)
```
╔══════════ ABILITIES ═══════════╗
║ Slots: 3 / 5                   ║
║                                 ║
║ [1] Leaping Strike    (1 slot) ║
║     Martial | Range: melee     ║
║ [2] Magic Missile     (1 slot) ║
║     Magical | MP: 8 | Range: 8 ║
║ [ ] Sleep             (1 slot) ║
║     Magical | MP: 12 | Range: 6║
║                                 ║
║ > cursor on selected ability    ║
║                                 ║
║ [b]ind to key  [f]orget         ║
║ [i]nspect  [Esc] close          ║
╚═════════════════════════════════╝
```

- 'b': bind selected ability to a key (prompt: "Press key to bind:")
- 'f': forget selected ability (confirm: "Forget Leaping Strike? y/n")
- 'i': show full description popup
- Up/Down: navigate

### Required Test Abilities

**Leaping Strike** (Martial)
- Slot cost: 1
- MP cost: 0
- Targeting: SingleTarget, range 6 (must have empty tile behind target)
- Effect:
  1. Player teleports to the tile directly behind the target (relative to player)
  2. Deals weapon damage * 1.5
  3. If no open tile behind target, ability fails: "No room to leap."
  4. Animate: brief flash at origin, player appears at destination
- Description: "Vault over an enemy, striking from behind for 150% damage."

**Magic Missile** (Magical)
- Slot cost: 1
- MP cost: 8
- Targeting: SingleTarget, range 8
- Effect:
  1. Fire a projectile along Bresenham line from player to target
  2. Projectile stops if it hits a wall (misses)
  3. Damage: 5 + Lore * 2 (not affected by weapon/Power)
  4. Always hits if line is clear (no accuracy roll)
  5. Animate: '*' character traveling along the line
- Description: "Hurl a bolt of magical energy. Damage scales with Lore."

**Sleep** (Magical)
- Slot cost: 1
- MP cost: 12
- Targeting: SingleTarget, range 6
- Effect:
  1. Apply Sleep status effect to target
  2. Duration: 300 MP
  3. Save check: caster Technique vs target Toughness
  4. No projectile — instant effect
- Description: "Put an enemy into magical slumber. Broken by damage."

### Projectile Animation
```cpp
struct ProjectileAnimation {
    char glyph;             // '*' for magic missile
    int color_pair;
    std::vector<Position> path;  // tiles the projectile passes through
    int frame_delay_ms = 40;
};
```

The engine computes the path; the frontend animates it. If the projectile
hits a wall, the path ends at the wall tile with a "fizzle" effect.

### Skill Book Integration
Skill books from Stage 6 now actually work:
- on_use: Check if player already knows the ability → "You already know this."
- Check if player has enough slots → "You don't have enough ability slots."
- Show confirm dialog → learn ability, consume book

**Gameplay encounter requirement:** Place at least one Skill Book on the map at
game start (on the hardcoded pre-Stage-9 map) so that a player can find it by
exploring. Use `skillbook_leaping_strike` — place it on a floor tile away from
the player start. Once procedural generation is active (Stage 9), skill books
should appear in the item pool for the Populator phase.

### AoE Computation (for future abilities)
```cpp
// Get all tiles in AoE centered on target
// radius = base_radius + Technique / 5
std::vector<Position> compute_aoe(Position center, float radius, const TileMap& map);

// Get all entities within the AoE
std::vector<EntityId> entities_in_aoe(
    const std::vector<Position>& aoe_tiles,
    const std::unordered_map<EntityId, Position>& positions
);
```

## Acceptance Criteria

1. Player can learn abilities from skill books
2. Learning consumes the skill book
3. Abilities show on ability screen with correct info
4. Abilities can be bound to keys and unbound
5. 'a' then bound key activates ability
6. Leaping Strike: teleports behind target, deals 1.5x damage
7. Leaping Strike: fails gracefully when no room behind target
8. Magic Missile: projectile animates along line, deals Lore-based damage
9. Magic Missile: stops at walls
10. Sleep: applies status effect with save check
11. MP is consumed on ability use
12. Insufficient MP prevents use
13. Movement bar is consumed on ability use
14. Abilities can be forgotten, freeing slots
15. Cannot learn abilities that would exceed slot cap

## Verification

Automated tests exercise the engine through the JSON-line test harness protocol
defined in `tests/conftest.py`.  The harness builds the project, starts
`test_harness`, and validates behavior by issuing commands and inspecting state.

---

## Goal
'f' to fire ranged weapon. Interactive targeting cursor with line-of-fire
visualization and tab-cycling through valid targets. AoE highlighting.
Perception-based accuracy falloff for ranged weapons.

## Deliverables

### Targeting System
```cpp
enum class TargetingContext {
    RangedWeapon,   // f-to-fire
    Ability,        // from ability activation
    Item            // from item use (wands, etc.)
};

struct TargetingState {
    bool active = false;
    TargetingContext context;
    Position cursor;                    // current cursor position
    std::vector<EntityId> valid_targets;  // tab-cycleable
    int current_target_index = -1;
    int max_range;
    float aoe_radius = 0;              // 0 = single target

    // Computed each frame
    std::vector<Position> line_of_fire; // Bresenham from player to cursor
    bool line_blocked;                  // does it hit a wall?
    std::vector<Position> aoe_tiles;    // tiles affected by AoE (if applicable)
    float hit_chance;                   // accuracy % for current target (0-100)
};

// Enter targeting mode
void begin_targeting(TargetingContext ctx, int range, float aoe_radius = 0);

// Targeting input
enum class TargetingCommand {
    MoveN, MoveNE, MoveE, MoveSE, MoveS, MoveSW, MoveW, MoveNW,
    Tab,        // cycle to next valid target
    ShiftTab,   // cycle to previous valid target
    Confirm,    // fire/use at current cursor position
    Cancel      // exit targeting mode
};

struct TargetingResult {
    bool confirmed;
    Position target;
    std::vector<EntityId> affected_entities;
};
```

### Targeting UI Rendering
```
Map viewport during targeting:
- Player '@' highlighted
- Cursor shown as 'X' or '+' blinking
- Line from player to cursor drawn with '·' or '-' '|' '/' '\'
- If line hits wall: line turns red at wall tile, cursor shows in red
- AoE radius: affected tiles get colored background (ncurses color pair)
- Valid targets in range: highlighted with distinct color
- Info bar at bottom: "Target: Goblin (8 tiles) | Tab: next target | Enter: fire | Esc: cancel"
```

ncurses implementation for AoE background coloring:
```cpp
// Define color pairs for AoE highlight
init_pair(AOE_PAIR, COLOR_WHITE, COLOR_RED);    // red background for AoE
init_pair(CURSOR_PAIR, COLOR_BLACK, COLOR_YELLOW); // yellow background for cursor
init_pair(LINE_PAIR, COLOR_CYAN, COLOR_BLACK);   // cyan for line of fire
init_pair(BLOCKED_PAIR, COLOR_RED, COLOR_BLACK);  // red for blocked line
```

### Ranged Weapon Mechanics
```cpp
struct RangedAttackResult {
    bool hit;
    int damage;
    float accuracy;         // computed accuracy at this range
    Position impact_point;  // where the projectile actually lands
    std::string description;
};

RangedAttackResult resolve_ranged_attack(
    const StatBlock& attacker_stats,
    const WeaponData& weapon,
    Position attacker_pos,
    Position target_pos,
    const TileMap& map,
    std::mt19937& rng
);

// Accuracy falloff formula:
// base_accuracy = 95%
// distance = manhattan or euclidean distance (use euclidean)
// perception_range = Perception stat
// if distance <= perception_range / 2: accuracy = base_accuracy
// if distance > perception_range / 2:
//   falloff_factor = (distance - perception_range/2) / (max_range - perception_range/2)
//   accuracy = base_accuracy * (1.0 - falloff_factor * 0.8)
//   clamped to minimum 15%
//
// Roll: uniform(0,100) < accuracy → hit
// On miss: projectile veers to random adjacent tile of target (cosmetic only, no friendly fire)

// Damage: same formula as melee (Power scaling) but uses ranged weapon base_damage
```

### Shortbow Update (from Stage 6)
Now fully functional:
- on_attack callback: enters targeting mode instead of melee
- 'f' key: if ranged weapon equipped, begin targeting
- If no ranged weapon: "You have no ranged weapon equipped."
- Animation: projectile char travels along line (like magic missile)

### Wand Item Type (optional stretch)
If time permits, add a wand that uses the targeting system:
- Wand of Fireballs: AoE targeting, radius 2
- Charges-based (5 charges, consumed on empty)
- Damage: 15 + Technique * 1 (AoE, no save)

### Integration with Ability System
Abilities from Stage 7 that use SingleTarget or AreaOfEffect targeting
should now use this targeting UI instead of auto-selecting.

Update Magic Missile: when cast, enters targeting mode. Player can aim.
Update Sleep: enters targeting mode, single target.

### Movement Cost
Firing a ranged weapon or confirming a targeted ability consumes
all remaining movement (same as melee attack).

## Acceptance Criteria

1. 'f' enters targeting mode when ranged weapon equipped
2. 'f' with no ranged weapon shows error message
3. Targeting cursor moves with arrow keys
4. Tab cycles through valid targets (enemies in range and LOS)
5. Line of fire drawn from player to cursor
6. Blocked lines (wall intersection) shown in red/different color
7. AoE radius shown with background coloring
8. Enter confirms, fires projectile
9. Esc cancels targeting, returns to normal play
10. Accuracy decreases with distance based on Perception
11. Misses show projectile veering off
12. Ranged attacks deal appropriate damage
13. Magic Missile and Sleep now use the targeting UI
14. Ranged attack consumes remaining movement bar

## Verification

Automated tests exercise the engine through the JSON-line test harness protocol
defined in `tests/conftest.py`.  The harness builds the project, starts
`test_harness`, and validates behavior by issuing commands and inspecting state.

---

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
