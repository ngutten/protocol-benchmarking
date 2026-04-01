"""Training tests for Stage 12: Multi-Tile Creatures."""


def test_multi_tile_occupancy(game):
    """A 2x2 creature occupies 4 tiles."""
    eid = game.spawn_creature("ogre", 10, 10, size={"w": 2, "h": 2})
    ent = game.get_entity(eid)
    body = ent.get("body", {})
    tiles = body.get("tiles", [])
    assert len(tiles) == 4


def test_multi_tile_spawn_position(game):
    """Ogre's body tiles cover the correct 2x2 area."""
    eid = game.spawn_creature("ogre", 10, 10, size={"w": 2, "h": 2})
    ent = game.get_entity(eid)
    body = ent.get("body", {})
    tiles = set(tuple(t) if isinstance(t, list) else (t["x"], t["y"])
                for t in body.get("tiles", []))
    expected = {(10, 10), (11, 10), (10, 11), (11, 11)}
    assert tiles == expected


def test_multi_tile_melee_from_edge(game):
    """Bumping any edge tile of a multi-tile creature triggers melee."""
    eid = game.spawn_creature("ogre", 7, 5, size={"w": 2, "h": 2})
    game.set_hp(eid, 200)
    hp_before = game.get_entity(eid).get("hp")
    assert hp_before is not None, "Entity must report hp"
    game.execute("MoveE")  # bump into ogre at (7,5)
    hp_after = game.get_entity(eid).get("hp")
    assert hp_after is not None, "Entity must report hp after attack"
    assert hp_after < hp_before
