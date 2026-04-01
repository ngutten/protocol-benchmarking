"""Holdout tests for Stage 4: FOV, Lighting, Map Memory.

These tests are NOT shown to the LLM during implementation.
They validate generalization beyond the training tests.
"""


def test_tile_memory(game):
    """Tiles become remembered after moving out of FOV range."""
    s = game.state()
    initial_visible = set(tuple(t) if isinstance(t, list) else (t["x"], t["y"])
                         for t in s["visible_tiles"])
    for _ in range(10):
        game.execute("MoveS")
    s2 = game.state()
    current_visible = set(tuple(t) if isinstance(t, list) else (t["x"], t["y"])
                          for t in s2["visible_tiles"])
    remembered = set(tuple(t) if isinstance(t, list) else (t["x"], t["y"])
                     for t in s2.get("remembered_tiles", []))
    # Tiles we could see before but can't now should be remembered
    left_fov = initial_visible - current_visible
    assert len(left_fov) > 0, "Moving 10 tiles south should leave some tiles out of FOV"
    assert left_fov.issubset(remembered), "Tiles that left FOV should be remembered"


def test_sound_detection(game):
    """Creature behind a wall within hearing range shows as heard."""
    # Build a wall between player (5,5) and skeleton at (5,2)
    game.set_tile(5, 4, "wall")
    game.set_tile(5, 3, "floor")
    game.set_tile(5, 2, "floor")
    eid = game.spawn_creature("skeleton", 5, 2)
    s = game.state()
    vis = s.get("creature_visibility", {})
    # Skeleton is 3 tiles away, behind a wall — should be Heard (not Visible)
    eid_str = str(eid)
    entry = vis.get(eid_str, vis.get(eid, {}))
    if isinstance(entry, str):
        assert entry == "Heard"
    else:
        assert entry.get("state") == "Heard"
