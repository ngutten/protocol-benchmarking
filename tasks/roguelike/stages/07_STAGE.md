# Stage 7 — Abilities, Ability Screen, Martial & Spell System

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
