# Stage 1 — Core Skeleton, Stats & Modifiers, Turn System & Enemies

## Goal
A running program: `@` walks around a hardcoded map. Side panel shows placeholders.
Message log at bottom. Main menu with New Game / Quit.

## Deliverables

### Data Structures
```cpp
enum class TileType { Floor, Wall, StairsUp, StairsDown, EdgeExit };

struct Position { int x, y; };

struct Tile {
    TileType type;
    char glyph;          // '#', '.', '<', '>', etc.
    bool walkable;
};

struct TileMap {
    int width, height;
    std::vector<Tile> tiles;  // row-major: tiles[y * width + x]
    Tile& at(int x, int y);
    const Tile& at(int x, int y) const;
};

enum class Command {
    MoveN, MoveNE, MoveE, MoveSE, MoveS, MoveSW, MoveW, MoveNW,
    Wait, OpenStatPanel, OpenInventory, OpenAbilities,
    Save, Quit,
    None  // no-op / unrecognized key
};

struct MessageLog {
    std::deque<std::string> messages;  // newest at back
    static constexpr int MAX_VISIBLE = 7;
    void add(const std::string& msg);
};

struct GameState {
    TileMap map;
    Position player_pos;
    MessageLog log;
    uint64_t seed;
    std::mt19937 rng;
    // Placeholder fields for later stages:
    // int hp, max_hp, mp, max_mp, level, xp, movement_bar, movement_max;
};

enum class ScreenMode { MainMenu, Game, StatPanel, Inventory, Abilities, Grave };

class GameEngine {
public:
    GameEngine(uint64_t seed);
    void new_game();
    const GameState& state() const;
    // Returns true if the command was processed (false = invalid/ignored)
    bool execute(Command cmd);
private:
    GameState state_;
    void move_player(int dx, int dy);
};
```

### Hardcoded Test Map
A 40×20 room with walls around the perimeter and a few internal walls.
Player starts at (5, 5). Include one staircase tile (non-functional in this stage).

### ncurses Frontend
```
┌─────────────────────────────────────┬───────────┐
│                                     │ HP: --/-- │
│         MAP VIEWPORT                │ MP: --/-- │
│                                     │ Lv: --    │
│              @                      │ Mv: --/-- │
│                                     │           │
│                                     │           │
├─────────────────────────────────────┤           │
│ Message log line 1                  │           │
│ Message log line 2                  │           │
│ ...                                 │           │
└─────────────────────────────────────┴───────────┘
```

- Map viewport: scrolls to keep `@` roughly centered on larger maps
- Side panel: right side, fixed width (~14 chars). Show placeholder values.
- Message log: bottom of map area, 7 lines, newest at bottom.
- Main menu: simple centered text, arrow keys to select, Enter to confirm.

### Input Mapping
```
Arrow keys / numpad → 4 cardinal directions
Numpad diagonals (7,9,1,3) or vi keys (yubn) → 4 diagonal directions
'.' or numpad 5 → Wait
'c' → Stat panel (placeholder screen, any key returns)
'i' → Inventory (placeholder screen)
'a' → Abilities (placeholder screen)
'S' → Save (stub: just log "Game saved")
'Q' → Quit (confirm prompt)
```

## Acceptance Criteria

1. Program launches, shows main menu with "New Game" and "Quit"
2. New Game starts, `@` appears on map
3. Player moves in 8 directions; walls block movement
4. Moving into a wall produces message "You bump into a wall."
5. Message log displays and scrolls correctly
6. Side panel renders with placeholder values
7. 'c', 'i', 'a' open placeholder screens that return on keypress
8. 'Q' prompts for confirmation, then exits
9. Terminal is properly cleaned up on exit (endwin)
10. Window resize is handled gracefully (re-render at new size)

## Build Requirements

The project must produce two executables:

1. **`roguelike`** — The full ncurses game (interactive play)
2. **`test_harness`** — A headless engine driver (**no ncurses dependency**) that
   accepts JSON-line commands on stdin and returns JSON-line responses on stdout.

Use CMake (`CMakeLists.txt`) or Make (`Makefile`). The build must support:
```
make test_harness   # builds only the headless test harness
make roguelike      # builds the ncurses game
make                # builds both
```

### Test Harness Protocol

The `test_harness` binary reads one JSON object per line from stdin and writes
one JSON object per line to stdout.  Every response includes `"ok": true` on
success or `"ok": false, "error": "..."` on failure.

**Commands for this stage:**

| Command | Parameters | Response fields |
|---------|-----------|----------------|
| `new_game` | `seed` (int) | `ok` |
| `execute` | `action` (string — a Command enum name, e.g. `"MoveE"`, `"MoveN"`, `"Wait"`, `"OpenStatPanel"`, `"OpenInventory"`, `"Quit"`) | `ok`, `accepted` (bool) |
| `state` | — | `ok`, `state` (see below) |
| `quit` | — | Clean process exit |

**State response fields for this stage:**
```json
{
  "ok": true,
  "state": {
    "player_pos": {"x": 5, "y": 5},
    "map": {"width": 40, "height": 20},
    "messages": ["Welcome!", "You bump into a wall."],
    "screen_mode": "Game",
    "seed": 42
  }
}
```

Subsequent stages extend the protocol with additional commands and state fields.
See `tests/conftest.py` for the full protocol definition used by automated tests.

## Reference Documents

The `reference/` directory contains cross-cutting design documents:
- `reference/00_OVERVIEW.md` — Architecture, engine/frontend split, core patterns
- `reference/KEYBOARD_REFERENCE.md` — All keybindings across all stages
- `reference/LIGHT_SOURCES.md` — Light source system specification (Stage 4+)

---

# Stage 2 — Stats, Modifier Stack, Stat Panel, Leveling

## Goal
Full stat system with the modifier stack architecture. Stat panel UI that displays
base stats, derived stats, equipment slots (empty), and handles level-up allocation.

## Deliverables

### Data Structures
```cpp
enum class StatType { Power, Mobility, Technique, Lore, Toughness, Perception };

enum class ModifierOp { Add, Multiply }; // applied in this order

struct Modifier {
    std::string source;     // e.g. "Ring of Light", "Potion of Strength", "Level 3"
    StatType stat;
    ModifierOp op;
    float value;            // +5 for Add, 1.2 for 20% Multiply
    int duration;           // movement points remaining; -1 = permanent/refreshable
    bool refreshed;         // for equipment: set true each turn, removed if false
};

struct ModifierStack {
    std::vector<Modifier> modifiers;

    void add(Modifier m);
    void remove_by_source(const std::string& source);
    void tick(int movement_points_consumed);  // decay durations
    void refresh(const std::string& source);  // mark as refreshed
    void cleanup_expired();                   // remove duration=0 and unrefreshed

    // Compute derived value from base
    float compute(float base_value) const;
    // Compute for a specific stat only
    float compute(float base_value, StatType filter) const;
};

struct StatBlock {
    // Base stats (only modified by level-up allocation)
    std::array<int, 6> base;  // indexed by StatType

    // Global modifier stack (all sources)
    ModifierStack modifiers;

    // Get effective stat value
    float effective(StatType s) const;

    // Derived stats (computed from effective stats)
    int max_hp() const;          // f(Toughness)
    int max_mp() const;          // f(Lore)
    int max_movement() const;    // f(Mobility)
    int vision_range() const;    // f(Perception)
    int carry_cap() const;       // f(Power)
    int ability_slots() const;   // f(Lore)
    float stealth() const;       // f(Mobility)
    float damage_mult() const;   // 1.0 + 0.05 * effective(Power)
    float effect_chance() const; // f(Technique)
    float aoe_size() const;      // f(Technique)
    float status_resist() const; // f(Toughness)
    float status_decay() const;  // f(Toughness), multiplier on tick rate
};

// Suggested derived stat formulas (tune as needed):
// max_hp       = 20 + Toughness * 8
// max_mp       = 5 + Lore * 4
// max_movement = 50 + Mobility * 5  (in abstract movement points)
// vision_range = 4 + Perception / 3
// carry_cap    = 20 + Power * 3     (in weight units)
// ability_slots= Lore / 2
// stealth      = Mobility * 0.5     (stealth score; see detection formula below)
//
// Detection formula (Stealth vs Perception):
//   detection succeeds when: Perception >= Stealth - distance
//   where Stealth = effective(Mobility) * 0.5
//   equivalently: detection_radius = Perception - Stealth
//   At base stats (both 10): detection_radius = 10 - 5 = 5 tiles
//   With Cloak of Shadows (+15 Mobility): Stealth = 12.5, radius = 10 - 12.5 = -2.5 (undetectable)
//   A perceptive enemy (Perc 15) vs base stealth: radius = 15 - 5 = 10 tiles
//   This replaces flat Stealth-vs-Perception comparison with distance-scaled detection.
// damage_mult  = 1.0 + 0.05 * Power (so at 10 Power = 1.5x)
// status_resist= Toughness * 3      (roll under to resist)
// status_decay = 1.0 + 0.03 * Toughness (multiplier on duration tick)

enum class EquipSlot { Head, Body, Hands, Feet, Back, Amulet, Ring1, Ring2, Weapon };

struct EquipmentSlots {
    std::array<EntityId, 9> equipped;  // indexed by EquipSlot; 0 = empty
};

// XP and leveling
struct LevelInfo {
    int level = 1;
    int xp = 0;
    int xp_to_next() const;       // e.g. level * 100
    bool can_level_up() const;
    int pending_points = 0;        // 2 per level-up, allocated by player
};
```

### Stat Panel UI (opened with 'c')

The stat panel uses a two-column layout to fit a typical terminal width (~80 cols)
without excessive vertical scrolling.

```
╔═══════════════════════ CHARACTER ════════════════════════╗
║ Level: 1    XP: 0/100            HP: 100/100  MP: 45/45 ║
║                                                          ║
║ ── Stats ──────────────────── ── Derived ────────────── ║
║   Power:      10  (eff: 10)    Damage Mult: 1.50x       ║
║   Mobility:   10  (eff: 10)    Max Movement: 100        ║
║   Technique:  10  (eff: 10)    Effect Chance: 50%       ║
║   Lore:       10  (eff: 10)    Ability Slots: 5         ║
║   Toughness:  10  (eff: 10)    Status Resist: 30        ║
║   Perception: 10  (eff: 10)    Vision Range: 7          ║
║                                Stealth: 5.0             ║
║                                Carry Cap: 50            ║
║                                                          ║
║ ── Equipment ─────────────── ── Equipment ───────────── ║
║   Head:    (empty)              Amulet:  (empty)         ║
║   Body:    (empty)              Ring 1:  (empty)         ║
║   Hands:   (empty)              Ring 2:  (empty)         ║
║   Feet:    (empty)              Weapon:  (empty)         ║
║   Back:    (empty)                                       ║
║                                                          ║
║ Gold: 0    Weight: 0/50                                  ║
╚══════════════════════════════════════════════════════════╝
```

Each derived stat is positioned next to a related base stat where possible,
so the player can see at a glance how base stats affect derived stats.

### Level-Up Flow
When `can_level_up()` is true:
1. Side panel shows "LEVEL UP!" indicator
2. Opening stat panel shows "You have 2 points to allocate."
3. A highlight cursor appears on the stats list (left column)
4. Player uses Up/Down arrows to select a stat, Enter to allocate a point
5. Stat increments, points remaining decrements, derived stats update live
6. When points exhausted, level increments, `xp_to_next` recalculates

If the player has banked enough XP for multiple levels, handle sequentially.

### Side Panel Update
Replace placeholder values from Stage 1:
```
HP: 100/100
MP:  45/45
Lv: 1
Mv: 100/100
[LEVEL UP!]      ← only when can_level_up()
```

## Acceptance Criteria

1. StatBlock computes all derived stats correctly from base values
2. ModifierStack correctly applies Add then Multiply operations
3. ModifierStack correctly removes expired/unrefreshed modifiers
4. Stat panel displays all stats, equipment slots, gold, weight
5. Effective stats differ from base when modifiers are active
6. Level-up flow works: allocate 2 points, level increments
7. Side panel shows real HP/MP/Level/Movement values
8. "LEVEL UP!" indicator appears when sufficient XP

## Verification

Automated tests exercise the engine through the JSON-line test harness protocol
defined in `tests/conftest.py`.  The harness builds the project, starts
`test_harness`, and validates behavior by issuing commands and inspecting state.

---

# Stage 3 — Turn System, Enemies, Basic AI

## Goal
The movement bar turn system is live. Two enemy types exist on the map, have AI that
detects and chases the player, and take turns after the player's bar empties.

## Deliverables

### Turn System Implementation
```cpp
struct MovementBar {
    int current;   // movement points remaining this round
    int maximum;   // derived from Mobility

    void reset();  // current = maximum
    bool empty() const { return current <= 0; }
    void spend(int cost);
};

// Movement costs (configurable per tile type)
constexpr int MOVE_COST_CARDINAL = 10;
constexpr int MOVE_COST_DIAGONAL = 14;
// Attack: consumes all remaining movement
// Ability: consumes all remaining movement
// Item use: consumes item-specified cost

struct TurnManager {
    enum class Phase { PlayerTurn, EnemyTurn, Animating };
    Phase phase = Phase::PlayerTurn;

    // Called when player's bar empties or player attacks
    void end_player_phase();

    // Process enemy turns in Mobility order
    // Returns a sequence of animations for the frontend
    struct Animation {
        EntityId entity;
        Position from, to;
        enum Type { Move, Attack, Death } type;
    };
    std::vector<Animation> process_enemy_turns();

    // Called after all enemies have acted
    void start_new_round();  // resets all bars
};
```

### Enemy Data
```cpp
enum class AIState { Idle, Chasing, Searching };

struct AIComponent {
    AIState state = AIState::Idle;
    Position last_known_player_pos;
    int search_turns_remaining = 0;
    int max_search_turns;        // configurable per creature type

    // Perception and detection
    int perception;              // vision range and detection ability
    bool can_see_player;         // updated each turn by FOV (simplified in this stage)
};

struct CreatureTemplate {
    std::string name;
    char glyph;
    StatBlock stats;
    int max_search_turns;
    int xp_reward;
};
```

### Two Test Enemies

**Goblin** (glyph: 'g')
- Stats: Pow 6, Mob 12, Tech 5, Lore 3, Tough 5, Perc 8
- Behavior: Detect at range 8, chase, search for 3 turns
- XP reward: 20
- Fast but weak. Gets multiple steps per turn.

**Skeleton** (glyph: 's')
- Stats: Pow 10, Mob 7, Tech 3, Lore 1, Tough 12, Perc 5
- Behavior: Detect at range 5, chase, search for 5 turns (persistent)
- XP reward: 35
- Slow but tough. Fewer steps per turn.

### AI Behavior (simplified for this stage)
FOV is not yet implemented (Stage 4), so use distance-based detection
with the stealth-vs-perception formula:

Detection formula:
  detection_radius = enemy_Perception - player_Stealth
  where player_Stealth = effective(Mobility) * 0.5
  Detection succeeds when: distance <= detection_radius
  AND line-of-sight check passes (Bresenham line, blocked by Wall tiles).

At base stats (Perception 10, Mobility 10): detection_radius = 10 - 5 = 5 tiles.
No light/darkness consideration yet (comes in Stage 4).

State machine:
```
Idle ──[sees player]──→ Chasing
  ↑                        │
  └──[search expired]──────┤
                           ↓
                       Searching ──[sees player]──→ Chasing
                           │
                    [turns expire]
                           ↓
                         Idle
```

Movement: A* pathfinding on the tile grid.
- Idle: don't move
- Chasing: path toward player
- Searching: path toward last_known_player_pos, decrement search counter each turn

### Animation System
When enemies move on-screen:
```cpp
struct AnimationQueue {
    std::vector<TurnManager::Animation> pending;
    int frame_delay_ms = 80;  // time between each enemy step

    bool has_pending() const;
    TurnManager::Animation next();
};
```

The frontend pulls animations one at a time, renders each with a brief delay.
Off-screen enemy actions are added to the queue but rendered instantly (no delay).

### A* Pathfinding
```cpp
// Returns next step toward goal, or nullopt if unreachable
std::optional<Position> find_path(
    const TileMap& map,
    Position from,
    Position to,
    const std::unordered_set<Position>& blocked  // positions occupied by entities
);
```

Use standard A* with 8-directional movement. Diagonal movement blocked if either
adjacent cardinal tile is a wall (no corner-cutting).

## Updated GameEngine Interface
```cpp
class GameEngine {
public:
    // ... previous interface ...

    // Execute a command. May trigger enemy phase.
    // Returns animations to play (empty if no enemy phase triggered).
    struct TurnResult {
        bool command_accepted;
        std::vector<TurnManager::Animation> animations;
        bool round_ended;  // true if a full round completed
    };
    TurnResult execute(Command cmd);

    // Entity management
    EntityId spawn_creature(const CreatureTemplate& tmpl, Position pos);
    const std::unordered_map<EntityId, Position>& entity_positions() const;
};
```

## Acceptance Criteria

1. Player movement costs correct amount from movement bar
2. When player bar empties (from movement) or player attacks (stub: bump into enemy),
   enemy phase triggers
3. Enemies act in descending Mobility order
4. Goblins take more steps per turn than Skeletons
5. Enemies detect player within their perception range (line of sight)
6. Detected enemies path toward player using A*
7. Enemies that lose sight of player search for N turns, then go idle
8. On-screen enemy movement animates at visible pace
9. Off-screen enemies resolve instantly
10. Movement bar and side panel update correctly
11. Multiple rounds cycle correctly

## Verification

Automated tests exercise the engine through the JSON-line test harness protocol
defined in `tests/conftest.py`.  The harness builds the project, starts
`test_harness`, and validates behavior by issuing commands and inspecting state.
