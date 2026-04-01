"""Training tests for Stage 1: Core Skeleton, Stats & Modifiers, Turn System & Enemies."""

MOVE_COST_CARDINAL = 10


# ---------------------------------------------------------------------------
# Core Skeleton
# ---------------------------------------------------------------------------

def test_new_game_starts(engine):
    """Engine accepts new_game and enters Game screen."""
    resp = engine.new_game(seed=42)
    assert resp["ok"]
    s = engine.state()
    assert s["screen_mode"] == "Game"


def test_player_start_position(game):
    """Player starts at (5, 5) on the hardcoded map."""
    s = game.state()
    assert s["player_pos"] == {"x": 5, "y": 5}


def test_move_east(game):
    """Moving east increases x by 1."""
    start = game.state()["player_pos"]
    game.execute("MoveE")
    pos = game.state()["player_pos"]
    assert pos["x"] == start["x"] + 1
    assert pos["y"] == start["y"]


def test_wall_collision(game):
    """Moving into a wall keeps position and logs a message."""
    # Move north repeatedly until hitting the perimeter wall
    for _ in range(50):
        prev = game.state()["player_pos"]
        game.execute("MoveN")
    pos = game.state()["player_pos"]
    assert pos == prev
    msgs = game.state()["messages"]
    assert any("wall" in m.lower() for m in msgs)


def test_wait_does_not_move(game):
    """Wait command keeps the player in place."""
    start = game.state()["player_pos"]
    game.execute("Wait")
    pos = game.state()["player_pos"]
    assert pos == start


# ---------------------------------------------------------------------------
# Stats & Modifiers
# ---------------------------------------------------------------------------

def test_base_stats_present(game):
    """State includes base stats array for all 6 stats."""
    s = game.state()
    assert "stats" in s
    base = s["stats"]["base"]
    assert len(base) == 6


def test_derived_max_hp(game):
    """max_hp = 20 + Toughness * 8.  At base 10: 100."""
    s = game.state()
    assert s["derived"]["max_hp"] == 100


def test_effective_equals_base_without_modifiers(game):
    """Without modifiers, effective stats equal base stats."""
    s = game.state()
    base_power = s["stats"]["base"][0]  # Power is index 0
    eff_power = s["stats"]["effective"][0]
    assert eff_power == base_power


def test_level_up_grants_points(game):
    """Setting XP to level threshold enables level-up with 2 points."""
    game.set_xp(100)
    s = game.state()
    assert s["level_info"]["pending_points"] == 2


# ---------------------------------------------------------------------------
# Turn System & Enemies
# ---------------------------------------------------------------------------

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
