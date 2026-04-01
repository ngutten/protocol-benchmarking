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
