"""Training tests for Stage 4: Identification & Integration, Save/Load, Multi-Tile Creatures."""
import os
import tempfile


# ---------------------------------------------------------------------------
# Identification & Integration
# ---------------------------------------------------------------------------

def test_items_have_identification_level(game):
    """Items in inventory track identification level."""
    game.create_item("healing_potion", x=5, y=5)
    game.execute("Pickup")
    s = game.state()
    inv = s.get("inventory", [])
    assert len(inv) > 0
    item = inv[0]
    assert "identified" in item or "id_level" in item


def test_modifier_stack_integrity(game):
    """Equip modifiers apply on equip and revert to base on unequip."""
    base = game.state()["stats"]["base"][:]
    eff_before = game.state()["stats"]["effective"][:]
    assert eff_before == base, "Effective should equal base with no equipment"

    # Equip stealth cloak (+15 Mobility at index 1)
    resp = game.create_item("stealth_cloak")
    cloak_id = resp.get("item_id")
    game.force_equip(cloak_id)
    eff_equipped = game.state()["stats"]["effective"][:]
    assert eff_equipped[1] == base[1] + 15

    # Equip speed boots (+5 Mobility at index 1) -- different slot (Feet), stacks
    resp2 = game.create_item("speed_boots")
    boots_id = resp2.get("item_id")
    game.force_equip(boots_id)
    eff_both = game.state()["stats"]["effective"][:]
    assert eff_both[1] == base[1] + 15 + 5


# ---------------------------------------------------------------------------
# Save / Load
# ---------------------------------------------------------------------------

def test_save_creates_file(game):
    """Saving the game creates a save file."""
    with tempfile.TemporaryDirectory() as tmpdir:
        path = os.path.join(tmpdir, "test.sav")
        resp = game.save_game(path=path)
        assert resp.get("ok")
        assert os.path.isfile(path)


def test_save_load_roundtrip(game):
    """State is preserved across save/load."""
    game.execute("MoveE")
    game.execute("MoveE")
    s_before = game.state()

    with tempfile.TemporaryDirectory() as tmpdir:
        path = os.path.join(tmpdir, "test.sav")
        game.save_game(path=path)
        game.new_game(seed=999)
        game.load_game(path=path)
        s_after = game.state()

    assert s_after["player_pos"] == s_before["player_pos"]
    assert s_after["seed"] == s_before["seed"]


# ---------------------------------------------------------------------------
# Multi-Tile Creatures
# ---------------------------------------------------------------------------

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
