# Stage 1 — Core Skeleton: Loop, Map, Movement, Rendering

## Goal
A running program: `@` walks around a hardcoded map. Side panel shows placeholders.
Message log at bottom. Main menu with New Game / Quit.

## Deliverables

### Data Structures
```cpp
enum class TileType { Floor, Wall, StairsUp, StairsDown, EdgeExit };

struct Position { int x, y; };

struct Tile {
    TileType type;
    char glyph;          // '#', '.', '<', '>', etc.
    bool walkable;
};

struct TileMap {
    int width, height;
    std::vector<Tile> tiles;  // row-major: tiles[y * width + x]
    Tile& at(int x, int y);
    const Tile& at(int x, int y) const;
};

enum class Command {
    MoveN, MoveNE, MoveE, MoveSE, MoveS, MoveSW, MoveW, MoveNW,
    Wait, OpenStatPanel, OpenInventory, OpenAbilities,
    Save, Quit,
    None  // no-op / unrecognized key
};

struct MessageLog {
    std::deque<std::string> messages;  // newest at back
    static constexpr int MAX_VISIBLE = 7;
    void add(const std::string& msg);
};

struct GameState {
    TileMap map;
    Position player_pos;
    MessageLog log;
    uint64_t seed;
    std::mt19937 rng;
    // Placeholder fields for later stages:
    // int hp, max_hp, mp, max_mp, level, xp, movement_bar, movement_max;
};

enum class ScreenMode { MainMenu, Game, StatPanel, Inventory, Abilities, Grave };

class GameEngine {
public:
    GameEngine(uint64_t seed);
    void new_game();
    const GameState& state() const;
    // Returns true if the command was processed (false = invalid/ignored)
    bool execute(Command cmd);
private:
    GameState state_;
    void move_player(int dx, int dy);
};
```

### Hardcoded Test Map
A 40×20 room with walls around the perimeter and a few internal walls.
Player starts at (5, 5). Include one staircase tile (non-functional in this stage).

### ncurses Frontend
```
┌─────────────────────────────────────┬───────────┐
│                                     │ HP: --/-- │
│         MAP VIEWPORT                │ MP: --/-- │
│                                     │ Lv: --    │
│              @                      │ Mv: --/-- │
│                                     │           │
│                                     │           │
├─────────────────────────────────────┤           │
│ Message log line 1                  │           │
│ Message log line 2                  │           │
│ ...                                 │           │
└─────────────────────────────────────┴───────────┘
```

- Map viewport: scrolls to keep `@` roughly centered on larger maps
- Side panel: right side, fixed width (~14 chars). Show placeholder values.
- Message log: bottom of map area, 7 lines, newest at bottom.
- Main menu: simple centered text, arrow keys to select, Enter to confirm.

### Input Mapping
```
Arrow keys / numpad → 4 cardinal directions
Numpad diagonals (7,9,1,3) or vi keys (yubn) → 4 diagonal directions
'.' or numpad 5 → Wait
'c' → Stat panel (placeholder screen, any key returns)
'i' → Inventory (placeholder screen)
'a' → Abilities (placeholder screen)
'S' → Save (stub: just log "Game saved")
'Q' → Quit (confirm prompt)
```

## Acceptance Criteria

1. Program launches, shows main menu with "New Game" and "Quit"
2. New Game starts, `@` appears on map
3. Player moves in 8 directions; walls block movement
4. Moving into a wall produces message "You bump into a wall."
5. Message log displays and scrolls correctly
6. Side panel renders with placeholder values
7. 'c', 'i', 'a' open placeholder screens that return on keypress
8. 'Q' prompts for confirmation, then exits
9. Terminal is properly cleaned up on exit (endwin)
10. Window resize is handled gracefully (re-render at new size)

## Build Requirements

The project must produce two executables:

1. **`roguelike`** — The full ncurses game (interactive play)
2. **`test_harness`** — A headless engine driver (**no ncurses dependency**) that
   accepts JSON-line commands on stdin and returns JSON-line responses on stdout.

Use CMake (`CMakeLists.txt`) or Make (`Makefile`). The build must support:
```
make test_harness   # builds only the headless test harness
make roguelike      # builds the ncurses game
make                # builds both
```

### Test Harness Protocol

The `test_harness` binary reads one JSON object per line from stdin and writes
one JSON object per line to stdout.  Every response includes `"ok": true` on
success or `"ok": false, "error": "..."` on failure.

**Commands for this stage:**

| Command | Parameters | Response fields |
|---------|-----------|----------------|
| `new_game` | `seed` (int) | `ok` |
| `execute` | `action` (string — a Command enum name, e.g. `"MoveE"`, `"MoveN"`, `"Wait"`, `"OpenStatPanel"`, `"OpenInventory"`, `"Quit"`) | `ok`, `accepted` (bool) |
| `state` | — | `ok`, `state` (see below) |
| `quit` | — | Clean process exit |

**State response fields for this stage:**
```json
{
  "ok": true,
  "state": {
    "player_pos": {"x": 5, "y": 5},
    "map": {"width": 40, "height": 20},
    "messages": ["Welcome!", "You bump into a wall."],
    "screen_mode": "Game",
    "seed": 42
  }
}
```

Subsequent stages extend the protocol with additional commands and state fields.
See `tests/conftest.py` for the full protocol definition used by automated tests.

## Reference Documents

The `reference/` directory contains cross-cutting design documents:
- `reference/00_OVERVIEW.md` — Architecture, engine/frontend split, core patterns
- `reference/KEYBOARD_REFERENCE.md` — All keybindings across all stages
- `reference/LIGHT_SOURCES.md` — Light source system specification (Stage 4+)
