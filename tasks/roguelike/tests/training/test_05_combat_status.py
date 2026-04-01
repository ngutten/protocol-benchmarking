"""Training tests for Stage 5: Melee Combat, Damage, Death, Status Effects."""


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
