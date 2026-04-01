# Stage 12 — Multi-Tile Creatures

## Goal
Support creatures that occupy more than one tile (e.g., 2×2 Ogre, 3×2 Dragon).
This affects rendering, pathfinding, combat, FOV, and AI. This is a standalone
stage because the complexity touches many systems.

## Deliverables

### Multi-Tile Data Model
```cpp
struct MultiTileBody {
    int width, height;                  // footprint in tiles
    std::vector<char> glyphs;          // row-major, display character per tile
    // glyphs.size() == width * height

    // Which tiles does this body occupy, given an origin (top-left)?
    std::vector<Position> occupied_tiles(Position origin) const;

    // Is a specific position part of this body?
    bool occupies(Position origin, Position query) const;

    // All tiles adjacent to the body (for melee attack range)
    std::vector<Position> adjacent_tiles(Position origin) const;
};

// CreatureTemplate gains an optional multi-tile body:
struct CreatureTemplate {
    // ... existing fields ...
    std::optional<MultiTileBody> body;  // nullopt = single tile (1x1)
};
```

### Multi-Tile Pathfinding
```cpp
std::optional<Position> find_path_multitile(
    const TileMap& map,
    Position origin,            // current top-left
    const MultiTileBody& body,
    Position goal,              // target top-left position
    const std::unordered_set<Position>& blocked
);
```

**Key differences from single-tile A*:**
1. **Validity check:** A candidate position is valid only if ALL tiles in the
   body footprint are walkable and unoccupied. This means checking
   `width * height` tiles per candidate, not just one.

2. **Diagonal movement:** Allowed only if all corner tiles that the body
   sweeps through are clear. For a 2×2 body moving NE, this means checking
   a 3×3 area at the intermediate positions.

3. **Corridor width:** The creature cannot enter corridors narrower than its
   smallest dimension. The pathfinder should detect this quickly (the first
   expansion into a narrow corridor will fail all validity checks).

4. **Goal tolerance:** The goal position for a multi-tile creature attacking
   a 1×1 entity is "any origin position where at least one body tile is
   adjacent to the target." This means A* should check for adjacency to
   goal, not equality with goal.

```cpp
// Adjacency check for multi-tile reaching a single-tile target
bool is_adjacent_to_target(Position origin, const MultiTileBody& body, Position target) {
    for (auto& adj : body.adjacent_tiles(origin)) {
        if (adj == target) return true;
    }
    return false;
}
```

### Multi-Tile Rendering
```cpp
// When rendering a multi-tile creature:
// 1. Get all occupied tiles
// 2. For each tile: if it's in player FOV → render glyph with creature color
// 3. If some tiles are visible and some aren't → partial visibility
//    (render visible tiles, leave others as whatever the underlying map shows)
// 4. '?' for heard multi-tile creatures: show single '?' at closest occupied tile
```

**Partial visibility example (2×2 Ogre, left column visible):**
```
O .       ← left tile visible, right tile behind wall/out of FOV
O .       ← same: player sees half the ogre
```

The player should be able to tell something large is there from the partial
view. The message log can say "You see part of a large creature."

### Multi-Tile Combat

**Player attacking multi-tile creature:**
- Bump into any edge tile of the creature → melee attack
- Ranged: any occupied tile is a valid target
- AoE: creature is affected if ANY of its tiles falls within the AoE
- Damage is applied to the creature once (it's one entity, not multiple)

**Multi-tile creature attacking player:**
- Can attack if ANY of its tiles is adjacent to the player
- Only one attack per turn (same as single-tile)
- Attack originates from the closest adjacent tile (for animation)

**Multi-tile creature attacking multi-tile creature:**
- Adjacent if any tile of creature A is adjacent to any tile of creature B

### Multi-Tile FOV and Detection

**Player seeing creature:**
- Creature is visible if ANY occupied tile is in player FOV
- Sound detection: distance = minimum distance from player to any occupied tile

**Creature seeing player:**
- Use FOV from each occupied tile? Too expensive.
- Simplification: compute FOV from the creature's "eye position" (center tile,
  or top-left for even dimensions). Range = creature's perception stat.
- If the creature can see the player from its eye position, it detects the player.

### Multi-Tile AI Adjustments

**State machine is unchanged** (Idle → Chasing → Searching → Idle).

**Movement:** Uses multi-tile pathfinding. The creature may need to
"route around" narrow corridors that a 1×1 creature could traverse.
If the path is completely blocked (all routes too narrow), the creature
stays in place and attacks if adjacent.

**Positioning:** When chasing, the goal is to get adjacent to the player.
When the creature reaches adjacency, it stops and attacks.

### Test Creatures

**Ogre** (2×2, glyph: 'O')
```
O O
O O
```
- Stats: Pow 18, Mob 5, Tech 3, Lore 1, Tough 18, Perc 6
- Behavior: Detect at range 6, chase, search for 4 turns
- XP reward: 100
- Very slow, very strong. Often blocked by narrow corridors.

**Gameplay encounter requirement:** The Ogre must actually spawn in the dungeon
during normal play. Add it to the PopulatorPhase creature pool with
`min_depth=3`, `max_depth=-1`, `weight=0.5`. On levels where it can spawn,
the map generator must ensure at least some 3-wide corridors and rooms ≥ 4×4
so the ogre has room to move and the player can encounter it organically.

**Map generation note:** To ensure 2×2 creatures are usable, at least some
corridors and rooms must be wide enough. The map generator (Stage 9) should
be configured to generate at least some 3-wide corridors and rooms ≥ 4×4
on levels where multi-tile creatures can spawn.

### Map Generator Update
```cpp
// When spawning multi-tile creatures in the PopulatorPhase:
// 1. Check that the spawn position is valid for the body footprint
// 2. Verify pathfinding connectivity: the creature can reach at least
//    one room from its spawn point (don't strand it in a dead end)
// 3. If placement fails after N attempts, skip this creature
```

## Acceptance Criteria

1. 2×2 creatures render correctly on map
2. All four tiles of a 2×2 creature block movement
3. Multi-tile pathfinding navigates wide corridors correctly
4. Multi-tile creatures cannot enter narrow (1-wide) corridors
5. Player can melee attack by bumping any edge tile
6. Ranged attacks can target any occupied tile
7. AoE affects multi-tile creature if any tile is in radius
8. Multi-tile creature attacks player when any tile is adjacent
9. Partially visible creatures render visible tiles only
10. Sound detection uses closest occupied tile for distance
11. Multi-tile creatures don't get stuck in unreachable positions
12. Creature death removes all occupied tiles from blocked set

## Verification

Automated tests exercise the engine through the JSON-line test harness protocol
defined in `tests/conftest.py`.  The harness builds the project, starts
`test_harness`, and validates behavior by issuing commands and inspecting state.
