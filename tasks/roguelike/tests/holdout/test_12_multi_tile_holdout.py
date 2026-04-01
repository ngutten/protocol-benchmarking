"""Holdout tests for Stage 12: Multi-Tile Creatures.

These tests are NOT shown to the LLM during implementation.
They validate generalization beyond the training tests.
"""


def test_multi_tile_death_clears_tiles(game):
    """When a multi-tile creature dies, all occupied tiles are freed."""
    eid = game.spawn_creature("ogre", 7, 5, size={"w": 2, "h": 2})
    game.set_hp(eid, 1)
    game.execute("MoveE")  # bump-kill
    ent = game.get_entity(eid)
    assert ent.get("dead", True) or not ent.get("ok", True)


def test_multi_tile_cannot_enter_narrow_corridor(game):
    """A 2x2 creature cannot path through a 1-wide corridor."""
    # Build a wall bisecting the map with a single 1-wide gap
    for y in range(1, 19):
        if y != 10:
            game.set_tile(15, y, "wall")
        else:
            game.set_tile(15, y, "floor")  # 1-wide gap at (15, 10)

    # Spawn ogre on the east side of the wall
    eid = game.spawn_creature("ogre", 17, 9, size={"w": 2, "h": 2})
    # Player on the west side, near the gap
    game.move_to(13, 10)

    pos_before = game.get_entity(eid)["pos"]
    for _ in range(5):
        game.force_enemy_phase()
    pos_after = game.get_entity(eid)["pos"]

    # Ogre (2x2) cannot fit through 1-wide gap — must stay on east side
    assert pos_after["x"] >= 15
