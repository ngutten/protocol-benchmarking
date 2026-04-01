"""Holdout tests for Stage 3: Turn System, Enemies, Basic AI.

These tests are NOT shown to the LLM during implementation.
They validate generalization beyond the training tests.
"""

MOVE_COST_DIAGONAL = 14


def test_diagonal_movement_cost(game):
    """Diagonal movement costs 14 movement points."""
    bar_before = game.state()["player_bar"]["current"]
    game.execute("MoveNE")
    bar_after = game.state()["player_bar"]["current"]
    assert bar_after == bar_before - MOVE_COST_DIAGONAL


def test_enemy_detection_range(game):
    """Goblin (Perc 8) detects player at close range but not far away."""
    # Goblin detection_radius = 8 - player_stealth(5) = 3
    eid = game.spawn_creature("goblin", 30, 5)
    game.force_enemy_phase()
    ai = game.ai_state(eid)
    assert ai["state"] == "Idle"  # too far

    game.move_to(28, 5)  # distance = 2, within range
    game.force_enemy_phase()
    ai = game.ai_state(eid)
    assert ai["state"] == "Chasing"


def test_mobility_order(game):
    """Goblin (Mob 12) acts before Skeleton (Mob 7) in enemy phase."""
    goblin_id = game.spawn_creature("goblin", 8, 5)
    skeleton_id = game.spawn_creature("skeleton", 12, 5)
    resp = game.force_enemy_phase()
    anims = resp.get("animations", [])
    goblin_first = None
    skeleton_first = None
    for i, a in enumerate(anims):
        if a.get("entity") == goblin_id and goblin_first is None:
            goblin_first = i
        if a.get("entity") == skeleton_id and skeleton_first is None:
            skeleton_first = i
    assert goblin_first is not None, "Goblin should produce at least one animation"
    assert skeleton_first is not None, "Skeleton should produce at least one animation"
    assert goblin_first < skeleton_first
