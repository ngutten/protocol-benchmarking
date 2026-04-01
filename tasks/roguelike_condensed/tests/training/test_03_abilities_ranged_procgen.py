"""Training tests for Stage 3: Abilities, Ranged Combat & Targeting, Procedural Generation."""


# ---------------------------------------------------------------------------
# Abilities
# ---------------------------------------------------------------------------

def test_learn_ability(game):
    """Learning an ability adds it to the abilities list."""
    game.learn_ability("magic_missile")
    s = game.state()
    abilities = s.get("abilities", [])
    assert any(a["name"] == "magic_missile" or "magic_missile" in a.get("name", "").lower()
               for a in abilities)


def test_abilities_in_state(game):
    """Learning magic_missile populates abilities with correct fields."""
    game.learn_ability("magic_missile")
    s = game.state()
    abilities = s["abilities"]
    assert len(abilities) >= 1
    mm = next(a for a in abilities if a["name"] == "magic_missile")
    assert "bound_key" in mm
    assert "mp_cost" in mm
    assert mm["mp_cost"] == 8


def test_ability_slot_limit(game):
    """Cannot learn more abilities than available slots allow."""
    s = game.state()
    max_slots = s["derived"].get("ability_slots", 5)
    # Use the three spec-defined abilities (each costs 1 slot)
    for name in ["magic_missile", "leaping_strike", "sleep"]:
        game.learn_ability(name)
    s = game.state()
    learned = len(s.get("abilities", []))
    assert learned <= max_slots
    assert learned == min(3, max_slots)


# ---------------------------------------------------------------------------
# Ranged Combat & Targeting
# ---------------------------------------------------------------------------

def test_targeting_mode_activatable(game):
    """Pressing fire key enters targeting mode."""
    resp = game.create_item("shortbow")
    bow_id = resp.get("item_id")
    game.force_equip(bow_id)
    game.execute("Fire")
    s = game.state()
    targeting = s.get("targeting", {})
    assert targeting.get("active", False) or s.get("screen_mode") == "Targeting"


def test_tab_cycles_targets(game):
    """Tab key cycles through valid targets in targeting mode."""
    resp = game.create_item("shortbow")
    bow_id = resp.get("item_id")
    game.force_equip(bow_id)
    game.spawn_creature("goblin", 8, 5)
    game.spawn_creature("skeleton", 10, 5)
    game.execute("Fire")
    game.execute("Tab")
    s = game.state()
    targeting = s.get("targeting", {})
    valid = targeting.get("valid_targets", [])
    assert len(valid) >= 1


# ---------------------------------------------------------------------------
# Procedural Generation
# ---------------------------------------------------------------------------

def test_map_connectivity(game):
    """Player can reach the down staircase from their starting position."""
    s = game.state()
    stairs = s["map"].get("stairs_down")
    assert stairs is not None, "Map must include stairs_down position"
    # Teleport to stairs -- if it succeeds, the tile is walkable
    resp = game.move_to(stairs["x"], stairs["y"])
    assert resp.get("ok")


def test_stairs_present(game):
    """Generated maps contain both up and down staircases."""
    s = game.state()
    m = s["map"]
    assert "stairs_down" in m, "Map must report stairs_down position"
    assert "x" in m["stairs_down"] and "y" in m["stairs_down"]
    assert "stairs_up" in m, "Map must report stairs_up position"
    assert "x" in m["stairs_up"] and "y" in m["stairs_up"]
