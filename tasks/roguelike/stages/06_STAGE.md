# Stage 6 — Items, Inventory, Equipment

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
