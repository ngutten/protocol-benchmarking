"""Holdout tests for Stage 9: Procedural Dungeon Generation.

These tests are NOT shown to the LLM during implementation.
They validate generalization beyond the training tests.
"""


def test_descend_stairs(game):
    """Using down stairs moves to next level."""
    s = game.state()
    level_before = s.get("dungeon_level", 0)
    stairs = s["map"].get("stairs_down")
    if stairs:
        game.move_to(stairs["x"], stairs["y"])
    game.execute("StairsDown")
    s2 = game.state()
    assert s2.get("dungeon_level", 0) == level_before + 1


def test_level_persistence(game):
    """Revisiting a level preserves its layout."""
    s1 = game.state()
    level = s1.get("dungeon_level", 0)
    map1 = s1["map"]
    game.set_level(level + 1)
    game.set_level(level)
    s2 = game.state()
    assert s2["map"] == map1


def test_population_scales_with_depth(game):
    """Deeper levels have more or tougher enemies."""
    game.set_level(1)
    s1 = game.state()
    entities1 = len(s1.get("entities", {}))
    game.set_level(5)
    s5 = game.state()
    entities5 = len(s5.get("entities", {}))
    assert entities5 >= entities1


def test_tile_memory_is_level_specific(game):
    """Descending twice: level 2 should NOT inherit remembered tiles from level 0.

    Memory is per-level.  After exploring level 0 and descending to level 2,
    the remembered_tiles on level 2 should only reflect what was seen on
    level 2, not carry over from previous levels.
    """
    # Explore level 0 — move around to build up some remembered tiles
    for _ in range(5):
        game.execute("MoveE")
    for _ in range(3):
        game.execute("MoveS")
    s0 = game.state()
    remembered_level0 = set(
        tuple(t) if isinstance(t, list) else (t["x"], t["y"])
        for t in s0.get("remembered_tiles", [])
    )
    assert len(remembered_level0) > 0, "Should have remembered tiles on level 0"

    # Descend to level 1
    stairs = s0["map"].get("stairs_down")
    if stairs:
        game.move_to(stairs["x"], stairs["y"])
    game.execute("StairsDown")
    assert game.state().get("dungeon_level", 0) == 1

    # Descend to level 2
    s1 = game.state()
    stairs = s1["map"].get("stairs_down")
    if stairs:
        game.move_to(stairs["x"], stairs["y"])
    game.execute("StairsDown")
    s2 = game.state()
    assert s2.get("dungeon_level", 0) == 2

    # Level 2: remembered tiles should be empty or near-empty (only what FOV
    # computed on arrival).  They should NOT contain the level 0 tiles.
    remembered_level2 = set(
        tuple(t) if isinstance(t, list) else (t["x"], t["y"])
        for t in s2.get("remembered_tiles", [])
    )
    # The level 0 remembered tiles are on a completely different map, so none
    # of them should appear as "remembered" on level 2 (maps differ in layout).
    # Even if coordinates overlap by chance, the count should be much smaller.
    overlap = remembered_level0 & remembered_level2
    assert len(overlap) < len(remembered_level0) // 2, \
        f"Level 2 should not inherit level 0's tile memory ({len(overlap)} overlapping " \
        f"out of {len(remembered_level0)} level 0 tiles)"


def test_items_on_generated_level(game):
    """Generated levels should contain items placed by the Populator."""
    game.set_level(1)
    s = game.state()
    ground = s.get("ground_items", [])
    assert len(ground) > 0, "Generated levels should have items on the ground"
