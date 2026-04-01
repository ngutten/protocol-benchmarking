# Stage 4 — Identification & Integration, Save/Load, Multi-Tile Creatures

## Goal
Refine the three-tier identification system. Integration testing across
all existing systems. Fix edge cases in interactions between equipment,
status effects, abilities, inventory, and combat.

## Deliverables

### Three-Tier Identification (refinement of Stage 6)

The identification system was introduced in Stage 6 with basic mechanics.
This stage polishes it into a complete feature.

```
Level 0 (unidentified):
  - Generic name ("Shimmering Potion", "Golden Ring")
  - Vague description
  - No stat details shown in inventory inspect
  - Category is visible (player can tell a ring from a sword)

Level 1 (basic identification):
  - True name ("Potion of Healing", "Ring of Light")
  - General function description
  - Basic stats visible (damage, armor, main effect)

Level 2 (detailed identification):
  - Full modifier details visible (exact numbers)
  - All special properties revealed
  - Callback descriptions visible ("On equip: creates light")

Level 3 (mastery):
  - Hidden properties revealed (if any — rare items may have a hidden bonus)
  - Lore text / flavor text
  - Optimal use hints
```

### Identification Methods

**Manual (active):** Press 'I' in inventory to attempt identification.
Lore check as defined in Stage 6.

**Auto-identification by use:** Track per-item-type usage count.
```cpp
struct ItemKnowledge {
    std::unordered_map<std::string, int> usage_count;  // item_internal_name → count
    std::unordered_map<std::string, int> equip_time;   // item_internal_name → total MP equipped

    // Auto-ID thresholds:
    // 10+ uses OR 500+ MP equipped → auto-identify to level 1
    // Level 2 and 3 always require manual identification
    bool should_auto_identify(const std::string& item_name) const;
};
```

**Auto-identification applies retroactively:** when a threshold is crossed,
ALL items of that type (in inventory, on ground on all levels) are updated.

### Item Display Based on ID Level

In inventory:
```
Level 0: "Shimmering Potion (0.5)"          — generic name, weight only
Level 1: "Potion of Healing (0.5, 50g)"     — true name, weight, value
Level 2: "Potion of Healing (0.5, 50g) [Heals 50 HP]"  — with effect
Level 3: "Potion of Healing (0.5, 50g) [Heals 50 HP] *Ancient brew*"
```

### Integration Test Scenarios

This stage's main deliverable beyond identification is comprehensive
integration testing. Create test scenarios exercising cross-system
interactions:

1. **Equip → Combat → Status → Unequip cycle**
2. **Inventory weight + equipment + containers**
3. **Ability + targeting + FOV interaction**
4. **Level-up during combat**
5. **Staircase + entity persistence**
6. **Light source + equipment + FOV**

See test cases below for specifics.

## Acceptance Criteria

1. Three-tier identification displays correct info at each level
2. Auto-identification triggers at correct thresholds
3. Auto-identification is retroactive (existing items update)
4. All six integration test scenarios pass
5. No orphaned modifiers in the stack after equip/deequip cycles
6. Status effects and equipment modifiers compose correctly
7. FOV correctly interacts with light sources during equip changes

## Verification

Automated tests exercise the engine through the JSON-line test harness protocol
defined in `tests/conftest.py`.  The harness builds the project, starts
`test_harness`, and validates behavior by issuing commands and inspecting state.

---

## Goal
Full save/load. Main menu shows Continue when save exists. Save from game
returns to menu. Quit saves and exits. Death archives save.
Seed specification on new game.

## Deliverables

### Save Data
```cpp
struct SaveData {
    // Header
    uint32_t version;
    uint64_t seed;
    std::string character_name;
    int turn_count;
    std::time_t save_timestamp;

    // RNG state — full mt19937 internal state
    // Use std::stringstream with operator<< / operator>> for portable serialization
    std::string rng_state_serialized;

    // Player state
    Position player_pos;
    int current_depth;
    StatBlock player_stats;
    HealthComponent player_health;
    int current_mp;
    LevelInfo level_info;
    EquipmentSlots equipment;
    Inventory inventory;
    AbilitySet abilities;
    StatusEffectManager player_effects;
    MovementBar player_bar;

    // Item knowledge (identification progress)
    ItemKnowledge knowledge;

    // All items (inventory, equipped, ground items across all levels)
    // Container items serialize their contents as a list of item entity IDs.
    // On load, container→contents references are rebuilt from this map.
    std::unordered_map<EntityId, ItemData> all_items;

    // Dungeon levels (all visited levels)
    std::unordered_map<int, DungeonLevel> levels;

    // All creatures (across all levels, including dead tracking for XP)
    std::unordered_map<EntityId, CreatureState> all_creatures;

    // Message log (last 100 messages)
    std::deque<std::string> log_messages;

    // Entity ID counter
    EntityId next_entity_id;

    // Death statistics (tracked even while alive)
    struct Stats {
        int enemies_killed = 0;
        int gold_collected = 0;
        int potions_used = 0;
        int abilities_used = 0;
        int deepest_level = 0;
    } play_stats;
};
```

### Serialization Format

Use JSON (nlohmann/json library). Advantages for a benchmark:
- Human-readable (debuggable)
- No custom parsing code
- Easy to add new fields without breaking old saves
- nlohmann/json has `to_json`/`from_json` ADL customization points

```cpp
// nlohmann/json integration pattern:
void to_json(nlohmann::json& j, const Position& p) {
    j = {{"x", p.x}, {"y", p.y}};
}
void from_json(const nlohmann::json& j, Position& p) {
    j.at("x").get_to(p.x);
    j.at("y").get_to(p.y);
}
// Repeat for StatBlock, ItemData, DungeonLevel, etc.
```

### Save File Location
```cpp
// Platform-appropriate save directory
std::string save_directory();  // e.g., ~/.roguelike/ or %APPDATA%/roguelike/
std::string save_path();       // save_directory() + "save.json"
std::string archive_path(std::time_t death_time);
    // save_directory() + "dead_YYYYMMDD_HHMMSS.json"
```

### SaveManager
```cpp
class SaveManager {
public:
    bool save(const GameEngine& engine, const std::string& filepath);
    bool load(GameEngine& engine, const std::string& filepath);
    void archive(const std::string& filepath);
    bool save_exists(const std::string& filepath = "");
    static constexpr uint32_t CURRENT_VERSION = 1;
};

// Save process:
// 1. Collect all state from GameEngine into SaveData
// 2. Serialize to JSON
// 3. Write to temp file
// 4. Rename temp file to save file (atomic on most filesystems)
// This prevents corrupted saves on crash during write.

// Load process:
// 1. Read JSON from file
// 2. Check version compatibility
// 3. Deserialize into SaveData
// 4. Reconstruct GameEngine state from SaveData
// 5. Re-register item callbacks (callbacks are code, not data)
// 6. Validate: run integrity checks (entity references valid, etc.)

// Archive process:
// 1. Rename save.json → dead_TIMESTAMP.json
// 2. Continue granting is now unavailable
```

### Main Menu Update
```
     ╔═══════════════════════╗
     ║   ROGUELIKE v1.0      ║
     ║                       ║
     ║   > New Game          ║
     ║     Continue          ║   ← only if save_exists()
     ║     Quit              ║
     ║                       ║
     ║   Seed: [________]    ║   ← optional, empty = random
     ╚═══════════════════════╝
```

Seed input: when "New Game" is selected, cursor moves to seed field.
Player can type digits (or leave empty for random). Enter confirms.
Random seed: use `std::random_device` to generate a 64-bit seed.

### Save/Quit Integration

**From game, press 'S' (Save):**
1. Show "Saving..." message
2. Serialize and write save file
3. Return to main menu
4. Main menu now shows "Continue"

**From game, press 'Q' (Quit):**
1. Prompt: "Save and quit? (y/n)"
2. On 'y': save, then exit program
3. On 'n': return to game
4. On Esc: return to game

**On player death:**
1. Show grave screen (from Stage 5)
2. Archive save file
3. Any key → main menu
4. "Continue" is now absent

### Grave Screen Update
```
     ╔═══════════════════════════╗
     ║         REST IN PEACE      ║
     ║                            ║
     ║      Here lies @           ║
     ║                            ║
     ║   Level 5 Adventurer       ║
     ║   Slain by a Skeleton      ║
     ║   on Dungeon Level 3       ║
     ║                            ║
     ║   Turns survived: 847      ║
     ║   Enemies slain: 23        ║
     ║   Gold collected: 1,245    ║
     ║   Deepest level: 4         ║
     ║   Seed: 42                 ║
     ║                            ║
     ║   Press any key...         ║
     ╚═══════════════════════════╝
```

### Version Compatibility
```cpp
// On load:
if (save_data.version > CURRENT_VERSION) {
    // Future save — can't load
    show_error("Save file is from a newer version.");
    return false;
}
if (save_data.version < CURRENT_VERSION) {
    // Old save — attempt migration
    migrate_save(save_data);  // version-specific upgrade logic
}
```

### RNG State Serialization
```cpp
// Serialize mt19937 state
std::string serialize_rng(const std::mt19937& rng) {
    std::stringstream ss;
    ss << rng;
    return ss.str();
}

// Deserialize
std::mt19937 deserialize_rng(const std::string& state) {
    std::mt19937 rng;
    std::stringstream ss(state);
    ss >> rng;
    return rng;
}
```

This preserves the exact RNG state, ensuring deterministic replay
continues correctly from the save point.

### Callback Re-registration
Item callbacks (`on_use`, `on_equip`, etc.) are `std::function` objects
stored by name. On load, the callback registry must be populated before
items are deserialized. This means:

```cpp
void GameEngine::load(const std::string& filepath) {
    register_all_item_callbacks();  // populate registry first
    register_all_ability_effects(); // populate ability registry
    SaveManager::load(*this, filepath);  // then load state
    // Now item callback names resolve to actual functions
}
```

## Acceptance Criteria

1. Game saves all state to JSON file
2. Game loads and restores all state from JSON file
3. Save file is atomic (temp file + rename)
4. Gameplay is identical before save and after load (same RNG state)
5. 'S' saves and returns to main menu
6. 'Q' saves and exits program
7. Death archives save file, removes "Continue" from menu
8. Seed can be specified at new game
9. Same seed produces identical games
10. Version check rejects incompatible saves
11. Save file is human-readable (JSON)
12. Callbacks are re-registered on load
13. Container contents survive save/load (items inside pouches are preserved)
14. Level-specific tile memory is saved and restored per dungeon level

## Verification

Automated tests exercise the engine through the JSON-line test harness protocol
defined in `tests/conftest.py`.  The harness builds the project, starts
`test_harness`, and validates behavior by issuing commands and inspecting state.

---

## Goal
Support creatures that occupy more than one tile (e.g., 2×2 Ogre, 3×2 Dragon).
This affects rendering, pathfinding, combat, FOV, and AI. This is a standalone
stage because the complexity touches many systems.

## Deliverables

### Multi-Tile Data Model
```cpp
struct MultiTileBody {
    int width, height;                  // footprint in tiles
    std::vector<char> glyphs;          // row-major, display character per tile
    // glyphs.size() == width * height

    // Which tiles does this body occupy, given an origin (top-left)?
    std::vector<Position> occupied_tiles(Position origin) const;

    // Is a specific position part of this body?
    bool occupies(Position origin, Position query) const;

    // All tiles adjacent to the body (for melee attack range)
    std::vector<Position> adjacent_tiles(Position origin) const;
};

// CreatureTemplate gains an optional multi-tile body:
struct CreatureTemplate {
    // ... existing fields ...
    std::optional<MultiTileBody> body;  // nullopt = single tile (1x1)
};
```

### Multi-Tile Pathfinding
```cpp
std::optional<Position> find_path_multitile(
    const TileMap& map,
    Position origin,            // current top-left
    const MultiTileBody& body,
    Position goal,              // target top-left position
    const std::unordered_set<Position>& blocked
);
```

**Key differences from single-tile A*:**
1. **Validity check:** A candidate position is valid only if ALL tiles in the
   body footprint are walkable and unoccupied. This means checking
   `width * height` tiles per candidate, not just one.

2. **Diagonal movement:** Allowed only if all corner tiles that the body
   sweeps through are clear. For a 2×2 body moving NE, this means checking
   a 3×3 area at the intermediate positions.

3. **Corridor width:** The creature cannot enter corridors narrower than its
   smallest dimension. The pathfinder should detect this quickly (the first
   expansion into a narrow corridor will fail all validity checks).

4. **Goal tolerance:** The goal position for a multi-tile creature attacking
   a 1×1 entity is "any origin position where at least one body tile is
   adjacent to the target." This means A* should check for adjacency to
   goal, not equality with goal.

```cpp
// Adjacency check for multi-tile reaching a single-tile target
bool is_adjacent_to_target(Position origin, const MultiTileBody& body, Position target) {
    for (auto& adj : body.adjacent_tiles(origin)) {
        if (adj == target) return true;
    }
    return false;
}
```

### Multi-Tile Rendering
```cpp
// When rendering a multi-tile creature:
// 1. Get all occupied tiles
// 2. For each tile: if it's in player FOV → render glyph with creature color
// 3. If some tiles are visible and some aren't → partial visibility
//    (render visible tiles, leave others as whatever the underlying map shows)
// 4. '?' for heard multi-tile creatures: show single '?' at closest occupied tile
```

**Partial visibility example (2×2 Ogre, left column visible):**
```
O .       ← left tile visible, right tile behind wall/out of FOV
O .       ← same: player sees half the ogre
```

The player should be able to tell something large is there from the partial
view. The message log can say "You see part of a large creature."

### Multi-Tile Combat

**Player attacking multi-tile creature:**
- Bump into any edge tile of the creature → melee attack
- Ranged: any occupied tile is a valid target
- AoE: creature is affected if ANY of its tiles falls within the AoE
- Damage is applied to the creature once (it's one entity, not multiple)

**Multi-tile creature attacking player:**
- Can attack if ANY of its tiles is adjacent to the player
- Only one attack per turn (same as single-tile)
- Attack originates from the closest adjacent tile (for animation)

**Multi-tile creature attacking multi-tile creature:**
- Adjacent if any tile of creature A is adjacent to any tile of creature B

### Multi-Tile FOV and Detection

**Player seeing creature:**
- Creature is visible if ANY occupied tile is in player FOV
- Sound detection: distance = minimum distance from player to any occupied tile

**Creature seeing player:**
- Use FOV from each occupied tile? Too expensive.
- Simplification: compute FOV from the creature's "eye position" (center tile,
  or top-left for even dimensions). Range = creature's perception stat.
- If the creature can see the player from its eye position, it detects the player.

### Multi-Tile AI Adjustments

**State machine is unchanged** (Idle → Chasing → Searching → Idle).

**Movement:** Uses multi-tile pathfinding. The creature may need to
"route around" narrow corridors that a 1×1 creature could traverse.
If the path is completely blocked (all routes too narrow), the creature
stays in place and attacks if adjacent.

**Positioning:** When chasing, the goal is to get adjacent to the player.
When the creature reaches adjacency, it stops and attacks.

### Test Creatures

**Ogre** (2×2, glyph: 'O')
```
O O
O O
```
- Stats: Pow 18, Mob 5, Tech 3, Lore 1, Tough 18, Perc 6
- Behavior: Detect at range 6, chase, search for 4 turns
- XP reward: 100
- Very slow, very strong. Often blocked by narrow corridors.

**Gameplay encounter requirement:** The Ogre must actually spawn in the dungeon
during normal play. Add it to the PopulatorPhase creature pool with
`min_depth=3`, `max_depth=-1`, `weight=0.5`. On levels where it can spawn,
the map generator must ensure at least some 3-wide corridors and rooms ≥ 4×4
so the ogre has room to move and the player can encounter it organically.

**Map generation note:** To ensure 2×2 creatures are usable, at least some
corridors and rooms must be wide enough. The map generator (Stage 9) should
be configured to generate at least some 3-wide corridors and rooms ≥ 4×4
on levels where multi-tile creatures can spawn.

### Map Generator Update
```cpp
// When spawning multi-tile creatures in the PopulatorPhase:
// 1. Check that the spawn position is valid for the body footprint
// 2. Verify pathfinding connectivity: the creature can reach at least
//    one room from its spawn point (don't strand it in a dead end)
// 3. If placement fails after N attempts, skip this creature
```

## Acceptance Criteria

1. 2×2 creatures render correctly on map
2. All four tiles of a 2×2 creature block movement
3. Multi-tile pathfinding navigates wide corridors correctly
4. Multi-tile creatures cannot enter narrow (1-wide) corridors
5. Player can melee attack by bumping any edge tile
6. Ranged attacks can target any occupied tile
7. AoE affects multi-tile creature if any tile is in radius
8. Multi-tile creature attacks player when any tile is adjacent
9. Partially visible creatures render visible tiles only
10. Sound detection uses closest occupied tile for distance
11. Multi-tile creatures don't get stuck in unreachable positions
12. Creature death removes all occupied tiles from blocked set

## Verification

Automated tests exercise the engine through the JSON-line test harness protocol
defined in `tests/conftest.py`.  The harness builds the project, starts
`test_harness`, and validates behavior by issuing commands and inspecting state.
