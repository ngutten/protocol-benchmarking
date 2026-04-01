# Stage 2 — FOV & Lighting, Combat & Status Effects, Items & Inventory

## Goal
Proper line-of-sight using shadowcasting. Light sources with their own FOV.
Tiles remembered after being seen. '?' for heard/recently-seen creatures.

## Deliverables

### FOV System
```cpp
// Recursive shadowcasting (8 octants)
// Returns set of visible positions from origin within max_range
std::unordered_set<Position> compute_fov(
    const TileMap& map,
    Position origin,
    int max_range
);

// The same algorithm is used for:
// 1. Player vision (origin = player_pos, range = vision_range from Perception)
// 2. Light sources (origin = light_pos, range = light_radius)
// 3. Enemy vision (origin = enemy_pos, range = enemy perception)
```

Use symmetric shadowcasting (where if A can see B, B can see A).
This prevents exploitable asymmetries.

### Tile Visibility States
```cpp
enum class Visibility {
    Unseen,     // never viewed; render as blank space
    Remembered, // previously seen; render glyph in dark/dim color
    Visible     // currently in FOV and lit; render normally
};

struct TileMemory {
    // Per-tile: what the player last saw here
    char remembered_glyph;
    bool has_memory = false;
};

struct VisionState {
    std::vector<Visibility> tile_visibility;  // same size as map
    std::vector<TileMemory> tile_memory;      // what player remembers

    // Recomputed each time player moves or light changes
    void update(const TileMap& map, Position player_pos, int vision_range,
                const std::vector<LightSource>& lights);
};

// IMPORTANT: VisionState is per-level.  Each DungeonLevel (Stage 9) stores its
// own tile_visibility and tile_memory.  When the player changes level via
// stairs, the engine switches to the target level's VisionState.  Memory from
// level 0 must NOT bleed into level 1, etc.  On first visit to a new level,
// all tiles start as Unseen.
```

### Lighting System
```cpp
struct LightSource {
    Position pos;
    int radius;
    EntityId source_entity;  // e.g. the ring, a torch on the wall, etc.
    bool carried;            // moves with entity if true
};

// Light computation:
// 1. Compute player FOV (what geometry the player can see)
// 2. For each light source, compute its FOV (what it illuminates)
// 3. A tile is Visible if: it's in player FOV AND (in player's natural sight range
//    OR illuminated by any light source whose FOV reaches it)
//
// This means: the player can see dark areas within their natural range,
// but light sources extend visibility beyond that range (if geometry allows).
// The player must have line-of-sight to the lit tile.
```

A design note: "natural sight range" vs light. The player always has vision within
their Perception-based range (think of it as darkvision / adapted eyes). Light sources
extend the effective range. In dark areas beyond natural range but within a light's
radius, the player can see IF they also have line-of-sight.

### Creature Visibility for Player
```cpp
enum class CreatureVisibility {
    NotKnown,       // player has no information
    Heard,          // detected via sound, not sight — show '?'
    RecentlySeen,   // was visible last turn, now not — show '?' briefly
    Visible         // in FOV and lit — show actual glyph
};

// Sound detection:
// Uses the same stealth-vs-perception formula but at double range:
//   sound_detection_radius = (Perception - target_Stealth) * 2
//   where target_Stealth = target_Mobility * 0.5
// Sound goes through walls (no LOS required), but is reduced by walls:
//   each wall tile on the Bresenham line adds +2 to effective distance.
// If a creature is within sound range but NOT visible, show '?'.
```

### Rendering Rules
| State | Foreground | Background | Glyph shown |
|-------|-----------|------------|-------------|
| Unseen | n/a | n/a | ' ' (space) |
| Remembered | Dark gray | Black | Tile glyph from memory |
| Visible (unlit) | Dim white | Black | Current tile glyph |
| Visible (lit) | Bright white | Black | Current tile glyph |
| Creature Visible | Creature color | Black | Creature glyph |
| Creature Heard | Yellow | Black | '?' |
| Creature RecentlySeen | Dark yellow | Black | '?' |

Use ncurses color pairs:
```cpp
init_pair(1, COLOR_WHITE, COLOR_BLACK);     // normal
init_pair(2, COLOR_YELLOW, COLOR_BLACK);    // heard/recent
init_pair(3, 8, COLOR_BLACK);              // dim (color 8 = dark gray on 256-color terms)
// Fallback for 8-color terminals: use A_DIM attribute
```

### Update to Enemy AI (from Stage 3)
Replace the simplified distance+Bresenham detection with proper FOV:
- Each enemy computes FOV on their turn using the same shadowcasting
- Detection range uses the stealth formula:
  detection_radius = enemy_Perception - player_Stealth
  where player_Stealth = player_effective_Mobility * 0.5
- The enemy can only detect the player within both its FOV AND detection radius
- Enemies are NOT affected by light (they know their own territory)
- This determines `can_see_player` for the AI state machine

## Acceptance Criteria

1. Player can only see tiles within FOV
2. Walls correctly block vision (no seeing through corners)
3. Previously-seen tiles render in dim/dark when out of FOV
4. Unseen tiles render as blank
5. Light sources extend visible area (test: ring of light equipped → larger visible area)
6. Light sources respect geometry (light doesn't go through walls)
7. Creatures outside FOV but within hearing range show as '?'
8. Creatures that were visible last turn but aren't now briefly show as '?'
9. Enemy AI now uses FOV-based detection instead of simple range
10. Symmetric shadowcasting: if player sees enemy, enemy sees player (same range)

## Verification

Automated tests exercise the engine through the JSON-line test harness protocol
defined in `tests/conftest.py`.  The harness builds the project, starts
`test_harness`, and validates behavior by issuing commands and inspecting state.

---

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

---

## Goal
Full item system with inventory UI, equipment changing stats, containers,
identification levels, and callback hooks. Implement the required test items.

## Deliverables

### Item Data Model
```cpp
enum class ItemCategory {
    Weapon, Helmet, BodyArmor, Gloves, Boots, Cloak, Amulet, Ring,
    Potion, Scroll, SkillBook, Wand, Container, Misc
};

// Callback hooks — these are std::function, registered by name in a global registry
using ItemCallback = std::function<void(GameEngine& engine, EntityId user, EntityId item)>;

struct ItemCallbackSet {
    std::string on_use_name;        // registry key; empty = not usable
    std::string on_equip_name;
    std::string on_deequip_name;
    std::string on_pickup_name;
    std::string on_drop_name;
    std::string on_attack_name;     // triggered when wielder attacks
};

struct ItemData {
    std::string internal_name;      // unique identifier for serialization
    ItemCategory category;
    EquipSlot equip_slot;           // which slot, if equippable; None for non-equipment
    char glyph;                     // display character on map

    // Base stats (for equipment)
    int armor_value = 0;
    int base_damage = 0;            // for weapons
    std::vector<Modifier> equip_modifiers;  // added to ModifierStack on equip

    // Identification
    int id_level = 0;               // 0=unidentified, 1/2/3=progressively identified
    std::array<int, 3> id_difficulty;  // Lore check required for each level
    std::array<std::string, 4> descriptions;  // [0]=unidentified, [1..3]=per level

    // Display names per identification level
    std::string unidentified_name;  // e.g. "Shimmering Potion"
    std::string identified_name;    // e.g. "Potion of Healing"

    // Physical
    float weight;
    int gold_value;
    int use_movement_cost;          // movement points consumed on use

    // Container
    bool is_container = false;
    float container_capacity = 0;   // max weight of contents
    std::vector<EntityId> contents; // items inside

    // Callbacks
    ItemCallbackSet callbacks;
};

// Callback registry
class ItemCallbackRegistry {
    std::unordered_map<std::string, ItemCallback> registry;
public:
    void register_callback(const std::string& name, ItemCallback fn);
    ItemCallback get(const std::string& name) const;
};

// Example registration:
// registry.register_callback("heal_50", [](GameEngine& e, EntityId user, EntityId item) {
//     e.heal_entity(user, 50);
//     e.consume_item(item);
//     e.log("You drink the potion and feel restored.");
// });
```

### Inventory System
```cpp
struct Inventory {
    std::vector<EntityId> items;    // items in bag (not equipped)
    float total_weight() const;
    bool can_add(const ItemData& item, float carry_cap) const;
};
```

### Equipment Logic
On equip:
1. Check slot availability (Ring1/Ring2: fill first empty, or prompt)
2. If slot occupied, swap (unequip old, equip new)
3. Call `on_deequip` for old item, `on_equip` for new item
4. New item's `equip_modifiers` are added to ModifierStack with `WhileEquipped` policy
5. Each turn start: refresh modifiers from all equipped items

On deequip:
1. Call `on_deequip`
2. Modifiers from this item will decay (not refreshed → cleaned up)
3. Item goes to inventory

### Identification System
```cpp
// Attempt to identify an item one level further
bool try_identify(EntityId item, int player_lore, std::mt19937& rng);

// Check: player_lore >= id_difficulty[current_level]
// If Lore is within 3 of difficulty, roll: success_chance = (Lore - diff + 3) * 15%
// If Lore >= difficulty + 3, auto-success
// If Lore < difficulty - 3, auto-fail
//
// On success: id_level++, description updates, name may change
// On failure: "You can't make out anything more about this item."
```

### Inventory Screen UI
```
╔══════════ INVENTORY ═══════════╗
║ Weight: 23.5 / 50.0            ║
║ Gold: 145                      ║
║                                 ║
║ > Potion of Healing       0.5  ║
║   Shimmering Potion       0.5  ║
║   Iron Sword              4.0  ║
║   Leather Pouch           1.0  ║
║     ├─ Ruby Gem           0.2  ║
║     └─ Gold Ring          0.1  ║
║   Scroll of ???           0.1  ║
║                                 ║
║ [e]quip  [u]se  [d]rop         ║
║ [i]nspect  [p]ut in  [t]ake out║
║ [Esc] close                     ║
╚═════════════════════════════════╝
```

Navigation:
- Up/Down arrow: move cursor
- Enter on container: expand/collapse contents
- 'e': equip selected (if equippable)
- 'u': use selected (calls on_use; if not usable, "You can't use that.")
- 'd': drop selected item to ground
- 'i': show description popup (based on id_level)
- 'p': put selected item into a container (see Put-In flow below)
- 't': take item out of container (see Take-Out flow below)
- Esc: close inventory

#### Put-In Flow ('p')

1. Player presses 'p' with cursor on a non-container item in the bag.
2. If there are no containers in the inventory: "You have no containers."
3. If there is exactly one container: use it automatically.
4. If there are multiple containers: show a lettered selection prompt:
   ```
   Put Iron Sword into which container?
     a) Leather Pouch (1.2 / 3.0)
     b) Large Sack   (5.0 / 10.0)
   ```
   Player presses 'a', 'b', etc. to select, or Esc to cancel.
5. If the item won't fit (weight exceeds remaining capacity): "That won't fit."
6. If the selected item is itself a container: "Containers cannot hold other containers."
7. If the selected item is equipped: "Unequip it first."
8. On success: item moves from bag list into the container's contents list.
   Message: "You put the Iron Sword in the Leather Pouch."

#### Take-Out Flow ('t')

1. Player presses 't' with cursor on an item **inside** a container
   (i.e., an indented item under a container in the tree view).
2. Item moves from the container's contents back to the top-level bag.
3. If the item would exceed the player's carry cap (container was reducing
   effective weight somehow — it shouldn't, but as a guard): "Your bag is too full."
4. On success: "You take the Gold Ring out of the Leather Pouch."
5. If 't' is pressed on a top-level item (not inside a container):
   "That item is not inside a container."

#### Inventory Execute Actions (test harness)

The following `execute` action strings operate while the inventory screen is open
(`screen_mode == "Inventory"`):

| Action | Behavior |
|--------|----------|
| `"InvUp"` / `"InvDown"` | Move cursor up/down |
| `"InvEquip"` | Equip selected item |
| `"InvUnequip"` | Unequip selected item |
| `"InvUse"` | Use selected item |
| `"InvDrop"` | Drop selected item |
| `"InvInspect"` | Show description popup |
| `"InvIdentify"` | Attempt Lore check on selected item |
| `"InvExpand"` | Expand/collapse container |
| `"InvPutIn"` | Begin put-in flow for selected item |
| `"InvTakeOut"` | Take selected item out of its container |
| `"InvSelectContainer"` | Select container by letter during put-in prompt (param: `"letter":"a"`) |
| `"CloseInventory"` | Close inventory, return to map |

When `InvPutIn` is issued and only one container exists, the put-in happens
immediately (no `InvSelectContainer` needed).  When multiple containers exist,
the engine enters `"container_select"` sub-mode and waits for
`InvSelectContainer`.

### Dialog System for Item Use
Some items need interaction beyond "consumed, done." The callback system
needs to be able to present simple dialogs:

```cpp
// Dialogs returned by callbacks; frontend renders them
struct Dialog {
    std::string message;
    enum Type { Confirm, TargetSelect, Info } type;
    // For Confirm: yes/no, returns bool
    // For TargetSelect: enters targeting mode, returns Position
    // For Info: just display, any key dismisses
};

// Callbacks can return a Dialog via engine:
// engine.show_dialog(Dialog{"Learn 'Magic Missile'? (y/n)", Dialog::Confirm});
// The engine queues this; frontend handles input; result fed back to engine.
```

### Required Test Items

### Action Names

The following actions are now valid for the `execute` command:
- `"Pickup"` — pick up item(s) from the player's tile (mapped to 'g')
- `"OpenInventory"` — open inventory screen (mapped to 'i', defined in Stage 1 as placeholder)
- `"Equip"` — equip the currently selected item in inventory UI
- `"Unequip"` — unequip the currently selected equipped item

### Required Test Items

Each item has an `internal_name` used by the test harness `create_item` command.

**Healing Potion** (internal_name: `"healing_potion"`, category: Potion)
- Unidentified: "Red Potion", Identified: "Potion of Healing"
- Weight: 0.5, Value: 50g
- ID difficulty: [5, -, -] (one level only)
- on_use: Heal 50 HP. Consumed on use. Movement cost: 20.
- Description[0]: "A potion filled with a red liquid."
- Description[1]: "A potion of healing. Restores health when consumed."

**Buff Potion** (internal_name: `"buff_potion"`, category: Potion)
- Unidentified: "Sparkling Potion", Identified: "Potion of Might"
- Weight: 0.5, Value: 75g
- on_use: Apply Strength status effect (+5 Power for 500 MP). Consumed. Cost: 20.

**Iron Sword** (internal_name: `"iron_sword"`, category: Weapon)
- Always identified (level 1 by default)
- Weight: 3.0, Value: 100g
- base_damage: 10, equip_slot: Weapon
- No special callbacks.

**Shortbow** (internal_name: `"shortbow"`, category: Weapon, ranged — comes fully alive in Stage 8)
- Weight: 2.0, Value: 120g
- base_damage: 8, equip_slot: Weapon
- on_attack: "ranged_attack" — in this stage, stub that logs "Ranged attacks come later."

**Iron Helmet** (internal_name: `"iron_helmet"`, category: Helmet)
- Weight: 2.5, Value: 60g
- armor_value: 3, equip_slot: Head
- equip_modifiers: none beyond armor

**Leather Armor** (internal_name: `"leather_armor"`, category: BodyArmor)
- Weight: 5.0, Value: 80g
- armor_value: 5, equip_slot: Body

**Leather Gloves** (internal_name: `"leather_gloves"`, category: Gloves)
- Weight: 0.5, Value: 30g
- armor_value: 1, equip_slot: Hands

**Ring of Light** (internal_name: `"ring_of_light"`, category: Ring)
- Weight: 0.1, Value: 200g
- ID difficulty: [8, 15, -]
- on_equip: Create a LightSource at player position, radius 8, carried=true
- on_deequip: Remove the light source
- Description[0]: "A golden ring that feels warm."
- Description[1]: "Ring of Light. Glows softly."
- Description[2]: "Ring of Light. Produces a magical light with radius 8."

**Cloak of Shadows** (internal_name: `"stealth_cloak"`, category: Cloak)
- Weight: 1.5, Value: 250g
- equip_slot: Back
- equip_modifiers: [{stat: Mobility, op: Add, value: 15}] (boosts stealth via Mobility)
  At base stats: Stealth goes from 5 to 12.5, making the player effectively undetectable
  by most enemies (detection_radius = Perception - 12.5, negative for enemies with Perc < 13)
- ID difficulty: [10, 18, 25]

**Boots of Swiftness** (internal_name: `"speed_boots"`, category: Boots)
- Weight: 1.0, Value: 180g
- equip_slot: Feet
- equip_modifiers: [{stat: Mobility, op: Add, value: 5}] (boosts movement bar)

**Leather Pouch** (internal_name: `"leather_pouch"`, category: Container)
- Weight: 0.3, Value: 10g
- is_container: true, capacity: 3.0

**Gold Ring** (internal_name: `"gold_ring"`, category: Ring)
- Always identified
- Weight: 0.1, Value: 50g
- equip_slot: Ring
- No modifiers or callbacks. A simple, non-magical ring.

**Skill Book: Leaping Strike** (internal_name: `"skillbook_leaping_strike"`, category: SkillBook — ability comes in Stage 7)
- Weight: 1.0, Value: 300g
- on_use: Dialog confirm "Learn Leaping Strike?", then teach ability. Consumed.

**Skill Book: Magic Missile** (internal_name: `"skillbook_magic_missile"`, category: SkillBook)
- on_use: Dialog confirm "Learn Magic Missile?", then teach ability. Consumed.

**Skill Book: Sleep** (internal_name: `"skillbook_sleep"`, category: SkillBook)
- on_use: Dialog confirm "Learn Sleep?", then teach ability. Consumed.

### Ground Items
Items can be on the ground (not in any inventory). Show them on the map with their glyph.
Player picks up with 'g' (get). If multiple items on same tile, show a pickup menu.

**Gameplay encounter requirement:** On the hardcoded Stage 1–8 map (before procedural
generation in Stage 9), the engine must place a small set of starter items on the
ground at game start so the player can organically find and interact with them.
At minimum, place:
- 1 Healing Potion on a floor tile
- 1 Iron Sword on a floor tile
- 1 Leather Pouch (container) on a floor tile
- 1 Gold Ring inside the Leather Pouch (demonstrating nested containers)

These should be placed deterministically based on the RNG seed, on floor tiles
away from the player start position. This ensures that a player exploring the
map will encounter items, pick them up, use containers, and equip gear — not
just pass tests that create items via the test harness.

### Container Operations via Test Harness

The test harness must support container manipulation for automated testing:

| Command | Parameters | Response |
|---------|-----------|----------|
| `put_in_container` | `item:int, container:int` | `ok` |
| `take_from_container` | `item:int, container:int` | `ok` |
| `container_contents` | `container:int` | `ok, items:[{id, name, weight}]` |

These correspond to the 'p' (put in) and 't' (take out) keyboard commands
in the inventory UI.

### Leather Pouch Details

The Leather Pouch (`"leather_pouch"`) is the primary test container:
- **Category:** Container
- **Weight:** 0.3 (empty weight; total weight = 0.3 + sum of contents)
- **Capacity:** 3.0 weight units
- **Behavior:**
  - Items placed inside count toward the pouch's capacity, not the top-level inventory
  - The pouch itself counts toward carry capacity (its weight + contents weight)
  - Items inside a container are NOT directly equippable — must be taken out first
  - Container contents are serialized as nested item references in save files
  - Attempting to put an item that exceeds remaining capacity logs: "That won't fit."
  - Containers cannot be placed inside other containers (no nesting of containers)

## Acceptance Criteria

1. Items can be picked up from ground, added to inventory
2. Inventory screen shows items with weight, allows navigation
3. Containers show nested contents with tree view
4. Items can be moved into/out of containers
5. Equipment changes modify stats through ModifierStack
6. Equipping Ring of Light creates a light source
7. Removing Ring of Light removes the light source
8. Cloak of Shadows measurably increases stealth stat
9. Boots of Swiftness increase movement bar max
10. Healing potion restores HP and is consumed
11. Buff potion applies temporary Strength modifier
12. Identification system works: Lore checks, progressive reveal
13. Item descriptions update with identification level
14. Skill books show confirm dialog (ability learning is Stage 7 stub)
15. Weight tracking prevents picking up items beyond carry cap
16. Drop puts items on ground at player position
17. Starter items placed on map at game start (Healing Potion, Iron Sword, Leather Pouch with Gold Ring)
18. Container put-in and take-out operations work via test harness commands
19. Container capacity enforcement prevents overfilling
20. Containers cannot be nested inside other containers

## Verification

Automated tests exercise the engine through the JSON-line test harness protocol
defined in `tests/conftest.py`.  The harness builds the project, starts
`test_harness`, and validates behavior by issuing commands and inspecting state.
