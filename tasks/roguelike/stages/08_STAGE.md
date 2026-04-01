# Stage 8 — Ranged Combat, Targeting Interface

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
