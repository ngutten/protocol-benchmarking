"""Training tests for Stage 8: Ranged Combat, Targeting Interface."""


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
