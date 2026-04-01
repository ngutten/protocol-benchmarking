# Keyboard Reference — All Screens

This document tracks every keyboard shortcut introduced at each stage.
It serves as the canonical reference for both implementation and testing.
When a stage introduces a new key binding, it is added here.

---

## Main Menu (Stage 1)

| Key | Action |
|-----|--------|
| Up/Down Arrow | Move selection cursor |
| Enter | Confirm selection |
| (typing in seed field) | Enter custom seed (Stage 11) |

Menu options: New Game, Continue (if save exists), Quit.

---

## Main Game Screen (Map View)

### Movement (Stage 1)

| Key | Action | Command Enum |
|-----|--------|-------------|
| Up Arrow / Numpad 8 / 'k' | Move North | `MoveN` |
| Down Arrow / Numpad 2 / 'j' | Move South | `MoveS` |
| Left Arrow / Numpad 4 / 'h' | Move West | `MoveW` |
| Right Arrow / Numpad 6 / 'l' | Move East | `MoveE` |
| Numpad 7 / 'y' | Move NW | `MoveNW` |
| Numpad 9 / 'u' | Move NE | `MoveNE` |
| Numpad 1 / 'b' | Move SW | `MoveSW` |
| Numpad 3 / 'n' | Move SE | `MoveSE` |
| '.' / Numpad 5 | Wait (spend MOVE_COST_CARDINAL from bar) | `Wait` |
| '5' (main keyboard) | End turn (dump remaining movement bar) | `EndTurn` |

Note: **Wait** spends one step's worth of movement. **End Turn** forfeits
all remaining movement and triggers the enemy phase immediately.
Both are needed: Wait lets you stand still while retaining remaining
movement (e.g., waiting for an enemy to come to you before attacking),
while End Turn is for when you're done and want enemies to go.

### Screen Navigation (Stage 1+)

| Key | Action | Introduced |
|-----|--------|-----------|
| 'c' | Open Character/Stat panel | Stage 1 |
| 'i' | Open Inventory screen | Stage 1 |
| 'A' (Shift+a) | Open Abilities screen | Stage 1 (stub), Stage 7 (functional) |
| 'S' | Save game (→ main menu) | Stage 1 (stub), Stage 11 (functional) |
| 'Q' | Quit (save + exit program) | Stage 1 |

### Interaction (Stage 3+)

| Key | Action | Introduced |
|-----|--------|-----------|
| (bump into enemy) | Melee attack | Stage 5 |
| 'g' | Pick up item from ground | Stage 6 |
| ',' | Pick up item (alias for 'g') | Stage 6 |
| 'a' | Begin ability activation (→ binding key) | Stage 7 |
| 'f' | Fire ranged weapon (→ targeting mode) | Stage 8 |
| '<' | Use stairs up (when standing on '<') | Stage 9 |
| '>' | Use stairs down (when standing on '>') | Stage 9 |

---

## Character/Stat Panel ('c')

### Stage 2 (introduced)

| Key | Action |
|-----|--------|
| Esc / 'c' | Close panel, return to map |
| Up/Down Arrow | Scroll if content overflows |

### Stage 2 (during level-up)

| Key | Action |
|-----|--------|
| Up/Down Arrow | Move highlight cursor between stats |
| Enter | Allocate point to highlighted stat |

### Stage 6 (equipment management from stat panel)

| Key | Action |
|-----|--------|
| Enter (on equipment slot) | Unequip item in this slot (→ inventory) |

---

## Inventory Screen ('i')

### Stage 6 (introduced)

| Key | Action |
|-----|--------|
| Up/Down Arrow | Move cursor |
| Esc / 'i' | Close inventory, return to map |
| 'e' | Equip selected item (if equippable) |
| 'u' | Use selected item (calls on_use) |
| 'U' | Unequip selected item (if equipped — shown in equipment section) |
| 'd' | Drop selected item to ground at player position |
| 'x' | Inspect selected item (show description based on id_level) |
| Enter | Expand/collapse container contents |
| 'p' | Put selected item into a container (see Put-In sub-flow) |
| 't' | Take item out of container (cursor must be on contained item) |
| 'I' | Attempt to identify selected item (Lore check) |

#### Put-In Sub-Flow ('p')

When the player presses 'p' on a bag item (not a container, not equipped):
1. If no containers in inventory → "You have no containers."
2. If exactly one container → item goes in immediately (no prompt).
3. If multiple containers → lettered selection appears:

| Key | Action |
|-----|--------|
| 'a', 'b', 'c', ... | Select container by letter |
| Esc | Cancel put-in |

On selection: item moves into chosen container if capacity allows.

#### Take-Out Sub-Flow ('t')

Pressing 't' on an indented (contained) item removes it from the container
and places it in the top-level bag. Pressing 't' on a top-level item shows
"That item is not inside a container."

Note: The inventory screen should show two sections:
1. **Equipped** — items currently in equipment slots, with slot labels
2. **Bag** — items in the bag (not equipped)

The player can 'U'nequip from the Equipped section (item moves to Bag)
and 'e'quip from the Bag section (item moves to slot).
'd'rop works from either section (unequips first if needed).

---

## Abilities Screen ('A')

### Stage 7 (introduced)

| Key | Action |
|-----|--------|
| Up/Down Arrow | Move cursor |
| Esc / 'A' | Close abilities screen |
| 'b' | Bind selected ability to a key (prompts: "Press key to bind:") |
| 'f' | Forget selected ability (confirm: "Forget X? y/n") |
| 'x' | Show full description of selected ability |
| 'u' | Unbind selected ability (remove key binding) |

---

## Ability Activation Mode (after pressing 'a' on map)

### Stage 7 (introduced)

| Key | Action |
|-----|--------|
| Bound key (e.g. '1', '2') | Activate bound ability |
| Esc | Cancel, return to map |

After activation, if ability requires targeting → enters Targeting Mode.
If self-targeted → executes immediately.

---

## Targeting Mode (ranged weapon 'f' or targeted ability)

### Stage 8 (introduced)

| Key | Action |
|-----|--------|
| Arrow keys / vi keys | Move targeting cursor |
| Tab | Cycle to next valid target |
| Shift+Tab | Cycle to previous valid target |
| Enter / Space | Confirm target, fire/use |
| Esc | Cancel, return to map |

Visual feedback during targeting:
- Line of fire drawn from player to cursor
- Blocked lines shown in red
- AoE radius shown with colored background
- Info bar shows target name, distance, hit chance (for ranged weapons)

---

## Pickup Menu (when multiple items on ground)

### Stage 6 (introduced)

| Key | Action |
|-----|--------|
| Up/Down Arrow | Move cursor |
| Enter / Space | Pick up selected item |
| 'a' | Pick up all items |
| Esc | Cancel, pick up nothing |

---

## Confirmation Dialogs

### Various stages

| Key | Action |
|-----|--------|
| 'y' | Confirm (yes) |
| 'n' | Deny (no) |
| Esc | Cancel (same as no) |

Used for: quit confirmation, forget ability, learn from skill book, etc.

---

## Grave Screen (Stage 5)

| Key | Action |
|-----|--------|
| Any key | Return to main menu |

---

## Command Enum Reference (for testing)

All player actions are represented as `Command` variants.
Tests issue these directly to the engine without going through key translation.

```cpp
enum class Command {
    // Movement
    MoveN, MoveNE, MoveE, MoveSE, MoveS, MoveSW, MoveW, MoveNW,
    Wait,           // spend one step of movement, don't move
    EndTurn,        // forfeit remaining movement, trigger enemy phase

    // Screen navigation
    OpenStatPanel,
    OpenInventory,
    OpenAbilities,

    // Map interactions
    PickUp,         // 'g' — pick up item from ground
    UseStairsUp,    // '<'
    UseStairsDown,  // '>'

    // Combat / abilities
    FireRanged,     // 'f' — begin ranged targeting
    BeginAbility,   // 'a' — enter ability activation mode

    // Meta
    Save,
    Quit,
    None            // no-op / unrecognized
};

// Subcommands (issued within specific modes, not from map screen)
enum class InventoryCommand {
    MoveUp, MoveDown,
    Equip, Unequip, Use, Drop, Inspect, Identify,
    ExpandContainer, PutIn, TakeOut,
    Close
};

enum class TargetingCommand {
    MoveN, MoveNE, MoveE, MoveSE, MoveS, MoveSW, MoveW, MoveNW,
    Tab, ShiftTab,
    Confirm, Cancel
};

enum class AbilityActivationCommand {
    SelectBinding(char key),
    Cancel
};

enum class StatPanelCommand {
    MoveUp, MoveDown,
    Confirm,                    // Enter: allocate point to highlighted stat
    UnequipSlot(EquipSlot slot),
    Close
};

enum class DialogCommand {
    Yes, No, Cancel
};
```

---

## Testing Interface Summary

### Headless Testing (no ncurses)
```cpp
GameEngine engine(seed);
engine.new_game();

// Map-screen commands
engine.execute(Command::MoveE);
engine.execute(Command::Wait);
engine.execute(Command::EndTurn);
engine.execute(Command::PickUp);

// Inventory mode
engine.open_inventory();
engine.inventory_command(InventoryCommand::MoveDown);
engine.inventory_command(InventoryCommand::Equip);
engine.inventory_command(InventoryCommand::Close);

// Ability activation
engine.execute(Command::BeginAbility);
engine.ability_select('1');  // press bound key
// → may enter targeting mode automatically
engine.targeting_command(TargetingCommand::Tab);
engine.targeting_command(TargetingCommand::Confirm);

// Stat panel
engine.execute(Command::OpenStatPanel);
engine.stat_panel_command(StatPanelCommand::MoveDown);   // highlight Power → Mobility
engine.stat_panel_command(StatPanelCommand::Confirm);     // allocate to Mobility
engine.stat_panel_command(StatPanelCommand::Close);

// Dialog responses
engine.dialog_command(DialogCommand::Yes);

// Direct state manipulation (test helpers, not game commands)
engine.set_player_hp(50);
engine.set_player_mp(10);
engine.move_player_to({x, y});
engine.spawn_creature(template, position);
engine.create_item(template);
engine.add_to_inventory(item_id);
engine.force_enemy_phase();
engine.advance_turn();
```

### Scripted Sequences (integration tests)
```cpp
// Record and replay
std::vector<Command> recording;
// ... play game, recording each command ...
// Replay on fresh engine with same seed
GameEngine replay_engine(same_seed);
replay_engine.new_game();
for (auto cmd : recording) {
    replay_engine.execute(cmd);
}
// Assert final state matches
```

### GUI Tests (optional)
Feed raw keystrokes to the ncurses frontend layer.
Capture screen buffer, compare against expected output.
```cpp
Frontend frontend(engine);
frontend.inject_key(KEY_RIGHT);  // move east
frontend.inject_key('g');        // pick up
frontend.inject_key('i');        // open inventory
auto screen = frontend.capture_screen();
EXPECT_TRUE(screen.contains_at(5, 10, "Iron Sword"));
```
