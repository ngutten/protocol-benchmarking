# Stage 5 — Melee Combat, Damage, Death, Status Effects

## Goal
Bump-to-attack combat works. Damage formula uses Power + weapon stats.
Creatures and player can die. Status effect system is live.
Game over flow on player death.

## Deliverables

### Combat System
```cpp
struct DamageResult {
    int raw_damage;        // before any reduction
    int final_damage;      // after armor/resistance
    bool killed;
    std::string description;  // "You hit the Goblin for 12 damage."
};

// Melee attack (bump-to-attack)
DamageResult resolve_melee_attack(
    const StatBlock& attacker_stats,
    const WeaponData* weapon,       // nullable: unarmed if nullptr
    const StatBlock& defender_stats,
    std::mt19937& rng
);

// Damage formula:
// base_damage = weapon_base_damage (or 1 + Power/5 for unarmed)
// scaled_damage = base_damage * (1.0 + 0.05 * attacker_Power)
// damage_roll = uniform(scaled_damage * 0.8, scaled_damage * 1.2)  // ±20% variance
// final_damage = max(1, damage_roll - defender_armor)
//
// Weapons can also have on_attack hooks (Stage 6).

struct WeaponData {
    int base_damage;
    int armor_value = 0;  // shields/armor
    // Other fields come in Stage 6
};
```

### Hit Points and Death
```cpp
struct HealthComponent {
    int current_hp;
    int max_hp;

    void take_damage(int amount);
    void heal(int amount);
    bool is_dead() const { return current_hp <= 0; }
};

// On creature death:
// 1. Remove from active entities
// 2. Drop loot (Stage 6)
// 3. Award XP to player
// 4. Log message: "The Goblin dies!"
// 5. Corpse tile remains for rendering (optional: '%' glyph)

// On player death:
// 1. Log message: "You die..."
// 2. Transition to Grave screen
// 3. Grave screen shows: character name, level, cause of death, turn count
// 4. Any key → return to main menu
// 5. Save file is archived (renamed with death timestamp)
```

### Status Effect System
```cpp
enum class StatusEffectType {
    // Negative
    Poison,       // damage over time
    Sleep,        // can't act; broken on damage
    Slow,         // reduced movement bar
    Blind,        // reduced vision range

    // Positive
    Haste,        // increased movement bar
    Regen,        // heal over time
    Strength,     // Power boost
    // Extensible: add more as needed
};

struct StatusEffect {
    StatusEffectType type;
    int duration_mp;              // movement points until expiry
    EntityId source;              // who applied it
    float magnitude;              // effect-specific value

    // Computed from Technique vs Toughness on application
    // Not stored — just used during the initial save check
};

struct StatusEffectManager {
    // Per-entity
    std::vector<StatusEffect> active_effects;
    std::unordered_set<StatusEffectType> immunities;  // temporary immunity after throw-off

    // Try to apply an effect. Returns true if applied.
    bool try_apply(StatusEffectType type, float magnitude, int duration_mp,
                   int attacker_technique, int defender_toughness,
                   std::mt19937& rng);

    // Tick: called when movement points are consumed
    // defender_toughness affects tick rate
    void tick(int mp_consumed, int defender_toughness);

    // Process ongoing effects (called each tick)
    // Returns events (damage ticks, effect expiry messages, etc.)
    struct EffectEvent {
        std::string message;
        int damage = 0;  // for poison/regen
    };
    std::vector<EffectEvent> process_tick();

    // Grant immunity to a type for one full movement bar
    void grant_immunity(StatusEffectType type, int bar_max);

    bool has_effect(StatusEffectType type) const;
    bool is_immune(StatusEffectType type) const;
};

// Application save check:
// success_chance = 50 + (attacker_Technique - defender_Toughness) * 5
// clamped to [5, 95] — always a small chance either way
// Roll uniform(0,100) < success_chance → applied
//
// Duration tick rate:
// effective_tick = mp_consumed * (1.0 + 0.03 * defender_Toughness)
// So high Toughness makes effects wear off faster

// Immunity:
// When an effect expires naturally (duration reaches 0), the entity
// gains immunity to that specific effect type for one movement bar
// (i.e., immunity_duration = movement_bar_max)
// Immunity ticks down the same way as effects.
// Reapplication while immune: silently fails, no message.
// Reapplication while active: does nothing (no stacking, no refresh).
```

### Status Effect Behaviors
| Effect | Behavior |
|--------|----------|
| Poison | Deal `magnitude` damage per 50 MP consumed |
| Sleep | Entity skips turn entirely; broken by any damage |
| Slow | Modifier: Movement bar max reduced by `magnitude`% |
| Blind | Modifier: Vision range reduced by `magnitude` |
| Haste | Modifier: Movement bar max increased by `magnitude`% |
| Regen | Heal `magnitude` HP per 50 MP consumed |
| Strength | Modifier: Power increased by `magnitude` |

Effects that modify stats use the ModifierStack from Stage 2 with `Duration(mp)` policy.
The StatusEffectManager is responsible for adding/removing the corresponding modifiers.

### Integration with Turn System
```
Player action → resolve combat → apply status effects → tick effects
                                                       → check deaths
Enemy action  → resolve combat → apply status effects → tick effects
                                                       → check deaths
```

### Side Panel Update
```
HP: 85/100 [POISONED]
MP:  45/45
Lv: 2
Mv:  60/100
```
Show active negative status effects on the HP/MP lines with color coding.

## Acceptance Criteria

1. Bumping into an enemy deals damage based on Power + weapon
2. Damage has ±20% variance
3. Enemies can damage the player
4. Creatures die at 0 HP, drop XP, show death message
5. Player death → Grave screen → Main menu
6. Save file is archived on death
7. Status effects apply based on Technique vs Toughness save
8. Status effects tick down based on movement points, accelerated by Toughness
9. Sleep prevents action and is broken by damage
10. Poison deals periodic damage
11. Buff effects (Haste, Strength) modify stats through ModifierStack
12. Immunity window prevents immediate reapplication after throw-off
13. Duplicate application while active does nothing

## Verification

Automated tests exercise the engine through the JSON-line test harness protocol
defined in `tests/conftest.py`.  The harness builds the project, starts
`test_harness`, and validates behavior by issuing commands and inspecting state.
