# Stage 11 — Save / Load System

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
