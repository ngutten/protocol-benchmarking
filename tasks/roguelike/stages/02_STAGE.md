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
