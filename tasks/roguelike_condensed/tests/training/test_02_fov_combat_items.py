"""Training tests for Stage 2: FOV & Lighting, Combat & Status Effects, Items & Inventory."""


# ---------------------------------------------------------------------------
# FOV & Lighting
# ---------------------------------------------------------------------------

def test_visible_tiles_present(game):
    """Player's FOV respects walls placed around them."""
    # Place walls to create a known FOV boundary
    game.set_tile(7, 5, "wall")   # wall 2 tiles east of player at (5,5)
    game.set_tile(5, 3, "wall")   # wall 2 tiles north
    s = game.state()
    visible = s["visible_tiles"]
    vis_set = set(tuple(t) if isinstance(t, list) else (t["x"], t["y"])
                  for t in visible)
    # Player's own tile is visible
    assert (5, 5) in vis_set
    # Tile between player and wall is visible
    assert (6, 5) in vis_set
    # Tile behind the east wall should not be visible
    assert (8, 5) not in vis_set


def test_player_position_visible(game):
    """Player's own tile is always visible."""
    s = game.state()
    pos = s["player_pos"]
    visible = s["visible_tiles"]
    assert [pos["x"], pos["y"]] in visible or {"x": pos["x"], "y": pos["y"]} in visible


def test_remembered_tiles_initially_empty(game):
    """Before moving, remembered_tiles list is empty or absent."""
    s = game.state()
    remembered = s.get("remembered_tiles", [])
    assert len(remembered) == 0


# ---------------------------------------------------------------------------
# Combat & Status Effects
# ---------------------------------------------------------------------------

def test_melee_damage(game):
    """Bumping an enemy deals damage based on Power."""
    eid = game.spawn_creature("goblin", 6, 5)
    ent_before = game.get_entity(eid)
    hp_before = ent_before.get("hp", ent_before.get("stats", {}).get("hp"))
    assert hp_before is not None, "Entity must report hp"
    game.execute("MoveE")  # bump-attack at (6,5)
    ent_after = game.get_entity(eid)
    hp_after = ent_after.get("hp", ent_after.get("stats", {}).get("hp"))
    assert hp_after is not None, "Entity must report hp after attack"
    assert hp_after < hp_before


def test_creature_death_awards_xp(game):
    """Killing a creature awards XP."""
    eid = game.spawn_creature("goblin", 6, 5)
    game.set_hp(eid, 1)
    xp_before = game.state()["level_info"]["xp"]
    game.execute("MoveE")  # bump-kill
    xp_after = game.state()["level_info"]["xp"]
    assert xp_after > xp_before


def test_status_effect_applied(game):
    """Applying sleep to a creature appears in its status effects."""
    eid = game.spawn_creature("goblin", 10, 5)
    game.apply_status(eid, "sleep", duration_mp=300, magnitude=1)
    ent = game.get_entity(eid)
    effects = ent.get("status_effects", [])
    assert any(e["type"] == "sleep" for e in effects)


# ---------------------------------------------------------------------------
# Items & Inventory
# ---------------------------------------------------------------------------

def test_inventory_in_state(game):
    """Creating items in inventory populates the inventory list."""
    game.create_item("iron_sword")   # no x,y -> directly in inventory
    game.create_item("gold_ring")
    s = game.state()
    inv = s["inventory"]
    assert len(inv) >= 2
    names = [item["name"].lower() for item in inv]
    assert any("sword" in n for n in names)
    assert any("ring" in n for n in names)


def test_create_item_on_ground(game):
    """Creating an item at a position places it on the ground."""
    resp = game.create_item("healing_potion", x=5, y=5)
    assert resp.get("ok")
    s = game.state()
    ground = s.get("ground_items", [])
    assert len(ground) > 0


def test_pickup_item(game):
    """Player can pick up items from their tile."""
    game.create_item("healing_potion", x=5, y=5)
    game.execute("Pickup")  # 'g' key
    s = game.state()
    assert len(s["inventory"]) > 0
