# Roguelike Benchmark Project — Overview

## Purpose
A multi-stage benchmark for implementing an ASCII roguelike game in C++ with ncurses.
Each stage is independently implementable and testable.

## Architecture: Engine / Frontend Split

The single most important architectural decision: **the game engine has zero ncurses dependency.**

```
┌──────────────────────────────────────────────────────┐
│  ncurses Frontend (thin)                             │
│  - Translates keypresses → Command enum              │
│  - Reads GameState, renders to terminal              │
│  - Handles UI modes (inventory, targeting, etc.)     │
└────────────────────┬─────────────────────────────────┘
                     │ Commands↓  State↑
┌────────────────────┴─────────────────────────────────┐
│  Game Engine (headless, testable)                     │
│  - Accepts Command, returns updated GameState         │
│  - All game logic lives here                         │
│  - Deterministic given same seed + command sequence   │
└──────────────────────────────────────────────────────┘
```

### Why
- Unit tests call engine directly, no terminal needed
- GUI tests feed scripted command sequences, assert on state
- Replay/determinism: record commands → replay identically
- Clear separation prevents UI logic from leaking into game rules

## Core Data Layout

Prefer structs-of-arrays / flat data where it matters for iteration, but don't over-engineer.
A pragmatic approach: entities are integer IDs, components are stored in maps or vectors
keyed by entity ID. Not a full ECS framework — just the pattern.

```cpp
using EntityId = uint32_t;

// Example: positions stored separately from stats
std::unordered_map<EntityId, Position>  positions;
std::unordered_map<EntityId, StatBlock> stats;
std::unordered_map<EntityId, Inventory> inventories;
std::unordered_map<EntityId, AIState>   ai_states;
```

This makes serialization straightforward: iterate each map, write key-value pairs.

## Determinism

- All randomness flows through a single RNG instance (e.g., `std::mt19937`)
- Seeded at game start; seed stored in save file
- RNG state is part of save state
- No use of `rand()`, `time()`, or other non-deterministic sources in game logic
- Frontend timing (animation delays) does NOT affect game state

## Turn Model: Movement Bar

Each entity has a `movement_bar` (max determined by Mobility stat).
At the start of each round, all bars reset.

**Player phase:**
- Player takes actions. Each step costs movement points. Attack/ability consumes remaining bar.
- Player can take multiple steps before acting offensively.
- **Wait** (`.` key): stand still, spend one step's worth of movement. Useful for
  letting enemies come to you while retaining remaining movement for an attack.
- **End Turn** (`5` key): forfeit all remaining movement immediately, triggering enemy phase.

**Enemy phase (triggered when player bar empties or player attacks):**
- Enemies act in descending Mobility order.
- Each enemy spends their bar: multiple steps allowed, one attack max.
- On-screen enemies animate sequentially at visible pace.
- Off-screen enemies resolve instantly.

**Turn boundary:**
- After all entities have acted, round counter increments.
- Status effect durations tick based on movement points consumed, not rounds.

## Modifier Stack System

Stats are never mutated directly. Each stat has:
- `base_value`: Set at character creation, modified only by level-up point allocation
- `modifiers[]`: A list of `{source, value, operation, duration_policy}`
- `derived_value`: Computed as `f(base_value, active_modifiers)`

Modifier operations: `Add`, `Multiply`, `Override` (applied in that order).

Duration policies:
- `Permanent` — level-up bonuses, curses
- `WhileEquipped` — equipment; refreshed each turn, decays if not refreshed
- `Duration(movement_points)` — status effects; ticks down as bars are consumed
- `Immunity(movement_points)` — prevents reapplication of a specific effect

The "refresh and decay" pattern for equipment: on each turn start, equipment re-applies
its modifiers. If the item was removed, the modifier has no refresh and is cleaned up.
This avoids needing explicit unequip cleanup.

## Status Effects

- Initial application: save check based on Technique (attacker) vs Toughness (defender)
- Duration: measured in movement points consumed
- Toughness increases tick rate (effect decays faster)
- No stacking: if effect already active, reapplication does nothing
- Immunity window: after an effect expires, the entity is immune to that specific effect
  for one full movement bar cycle

## Save / Load

Save file contains:
- Random seed + current RNG state
- All entity data (position, stats, inventory, AI state, etc.)
- All map data (generated levels are persistent)
- Current level index
- Message log (last N messages)
- Turn/round counter

Format: binary or JSON — implementer's choice, but must be versioned.

On death: show grave screen, archive save file (rename, don't delete), return to menu.

## Map / Level Model

- Levels are generated on first visit, then persisted
- Each level has up/down staircases and optional edge exits
- Entities on non-active levels do NOT take turns; effects do NOT tick
- Levels are stored as 2D tile grids + entity lists
- See LIGHT_SOURCES.md for the light source system (carried, fixed, dropped)

## File Organization (suggested)

```
src/
  engine/
    types.h          — EntityId, enums, basic structs
    command.h        — Command enum
    stat_block.h     — StatBlock, ModifierStack
    entity.h         — Entity component storage
    inventory.h      — Item, Container, Inventory
    ability.h        — Ability, AbilitySet
    map.h            — TileMap, FOV, lighting
    combat.h         — Damage calc, status effects
    ai.h             — AI state machine, pathfinding
    mapgen.h         — Procedural generation
    engine.h         — GameEngine (the main interface)
    save.h           — Serialization
  frontend/
    renderer.h       — ncurses rendering
    input.h          — Keypress → Command translation
    ui_screens.h     — Stat panel, inventory, ability screen
    main.cpp         — Entry point
  tests/
    test_harness.h   — Headless test runner
    test_*.cpp       — Per-stage test files
```

## Testing Strategy

### Unit Tests (headless, no ncurses)
```cpp
// Create engine, issue commands, assert on state
GameEngine engine(seed);
engine.execute(Command::MoveNorth);
engine.execute(Command::MoveNorth);
assert(engine.state().player_pos == Position{5, 3});
```

### Integration Tests (scripted sequences)
```cpp
// Load a known map, run a full combat sequence
GameEngine engine(seed);
engine.load_test_scenario("two_goblins_in_room");
auto result = engine.execute_sequence({
    Command::MoveEast, Command::MoveEast, Command::Attack
});
assert(result.entities_killed > 0);
```

### GUI Tests (optional, for rendering validation)
Feed keypress sequences to the frontend, capture terminal output,
diff against expected screenshots. Useful but not required for correctness.

## Stages

See individual stage files (01_STAGE.md through 12_STAGE.md) for detailed specs.
See also: KEYBOARD_REFERENCE.md (all keybindings), LIGHT_SOURCES.md (light system spec).

| Stage | Focus | Key Deliverable |
|-------|-------|-----------------|
| 1  | Skeleton: loop, map, movement, rendering | Walking @ on a map |
| 2  | Stats, derived stats, stat panel, leveling | Full stat UI |
| 3  | Turn system, enemies, basic AI | Enemies that chase |
| 4  | FOV, lighting, map memory | Shadowcasting + light |
| 5  | Combat, damage, death, status effects | Bump-to-attack works |
| 6  | Items, inventory, equipment | Loot and gear |
| 7  | Abilities, ability screen, spells | Magic missile flies |
| 8  | Ranged combat, targeting UI | f-to-fire works |
| 9  | Procedural generation | Dungeon levels |
| 10 | Identification polish, integration testing | Cross-system correctness |
| 11 | Save/load, main menu, death flow | Persistence |
| 12 | Multi-tile creatures | 2×2+ enemies work everywhere |
