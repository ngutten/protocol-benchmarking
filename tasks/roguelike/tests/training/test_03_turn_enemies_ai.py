"""Training tests for Stage 3: Turn System, Enemies, Basic AI."""

MOVE_COST_CARDINAL = 10


def test_movement_bar_present(game):
    """State includes player movement bar with current and max."""
    s = game.state()
    assert "player_bar" in s
    assert "current" in s["player_bar"]
    assert "max" in s["player_bar"]


def test_cardinal_movement_cost(game):
    """Cardinal movement costs 10 movement points."""
    bar_before = game.state()["player_bar"]["current"]
    game.execute("MoveE")
    bar_after = game.state()["player_bar"]["current"]
    assert bar_after == bar_before - MOVE_COST_CARDINAL


def test_spawn_creature(game):
    """Can spawn a goblin and it appears in entity list."""
    eid = game.spawn_creature("goblin", 10, 5)
    assert eid is not None
    s = game.state()
    assert str(eid) in s["entities"] or eid in [e.get("id") for e in s.get("entities", {}).values()]


def test_enemy_phase_triggers_on_bar_empty(game):
    """When player bar empties, enemy phase triggers with animations."""
    game.spawn_creature("goblin", 10, 5)
    result = None
    for _ in range(50):
        result = game.execute("MoveE")
        if result.get("round_ended"):
            break
    assert result is not None
    assert result.get("round_ended", False)
