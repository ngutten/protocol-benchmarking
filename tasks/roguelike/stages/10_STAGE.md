# Stage 10 — Identification System Polish, Integration Pass

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
