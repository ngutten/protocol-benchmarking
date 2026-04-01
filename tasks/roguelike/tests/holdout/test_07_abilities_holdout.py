"""Holdout tests for Stage 7: Abilities, Ability Screen, Martial & Spell System.

These tests are NOT shown to the LLM during implementation.
They validate generalization beyond the training tests.
"""


def test_magic_missile_costs_mp(game):
    """Using Magic Missile consumes 8 MP."""
    game.learn_ability("magic_missile")
    game.spawn_creature("goblin", 10, 5)
    s = game.state()
    mp_before = s.get("mp", s["derived"]["max_mp"])

    # Activate ability: 'a' then bound key
    game.execute("ActivateAbility")
    abilities = s["abilities"]
    key = [a["bound_key"] for a in abilities if a["name"] == "magic_missile"][0]
    game.execute(key)
    # Target the goblin and confirm
    game.execute("Tab")
    game.execute("Confirm")

    s2 = game.state()
    mp_after = s2.get("mp", s2["derived"]["max_mp"])
    assert mp_after == mp_before - 8


def test_leaping_strike(game):
    """Leaping Strike teleports behind target and deals bonus damage."""
    game.learn_ability("leaping_strike")
    eid = game.spawn_creature("goblin", 9, 5)
    game.set_hp(eid, 100)
    hp_before = game.get_entity(eid)["hp"]

    # Activate ability
    game.execute("ActivateAbility")
    abilities = game.state()["abilities"]
    key = [a["bound_key"] for a in abilities if a["name"] == "leaping_strike"][0]
    game.execute(key)
    # Target the goblin and confirm
    game.execute("Tab")
    game.execute("Confirm")

    # Player was at (5,5), goblin at (9,5)
    # "Behind" target relative to player = one tile past goblin = (10,5)
    pos = game.state()["player_pos"]
    assert pos["x"] == 10 and pos["y"] == 5

    # Goblin should have taken damage (1.5x weapon damage)
    hp_after = game.get_entity(eid)["hp"]
    assert hp_after < hp_before
