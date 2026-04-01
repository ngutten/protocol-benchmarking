"""Holdout tests for Stage 5: Melee Combat, Damage, Death, Status Effects.

These tests are NOT shown to the LLM during implementation.
They validate generalization beyond the training tests.
"""


def test_creature_death_message(game):
    """Killing a creature logs a death message."""
    eid = game.spawn_creature("goblin", 6, 5)
    game.set_hp(eid, 1)
    game.execute("MoveE")
    msgs = game.state()["messages"]
    assert any("die" in m.lower() or "kill" in m.lower() or "defeat" in m.lower()
               for m in msgs)


def test_player_death_grave_screen(game):
    """Player dying transitions to the Grave screen."""
    game.set_hp(0, 0)  # player HP to 0
    s = game.state()
    assert s.get("screen_mode") == "Grave" or s.get("player_dead", False)


def test_damage_has_variance(engine):
    """Multiple attacks with same setup produce different damage values."""
    damages = []
    for seed in range(10):
        engine.new_game(seed=seed)
        eid = engine.spawn_creature("goblin", 6, 5)
        hp_before = engine.get_entity(eid).get("hp", 50)
        engine.execute("MoveE")
        hp_after = engine.get_entity(eid).get("hp", 50)
        if hp_before is not None and hp_after is not None:
            damages.append(hp_before - hp_after)
    assert len(set(damages)) >= 2


def test_melee_attack_logs_message(game):
    """Attacking an enemy logs a hit message with damage amount."""
    eid = game.spawn_creature("goblin", 6, 5)
    game.execute("MoveE")  # bump-attack
    msgs = game.state()["messages"]
    assert any("hit" in m.lower() or "damage" in m.lower() or "attack" in m.lower()
               for m in msgs), \
        f"Melee attack should log a hit message. Messages: {msgs}"


def test_status_effect_message(game):
    """Applying a status effect logs a message about the effect."""
    game.apply_status(0, "poison", duration_mp=300, magnitude=5)
    msgs = game.state()["messages"]
    assert any("poison" in m.lower() for m in msgs), \
        f"Applying poison should log a message. Messages: {msgs}"
