"""Holdout tests for Stage 1: Core Skeleton, Stats & Modifiers, Turn System & Enemies.

These tests are NOT shown to the LLM during implementation.
They validate generalization beyond the training tests.
"""

MOVE_COST_DIAGONAL = 14


# ---------------------------------------------------------------------------
# Core Skeleton
# ---------------------------------------------------------------------------

def test_map_dimensions(game):
    """Hardcoded map is 40x20."""
    s = game.state()
    assert s["map"]["width"] == 40
    assert s["map"]["height"] == 20


def test_diagonal_movement(game):
    """Moving NE changes both x+1 and y-1."""
    start = game.state()["player_pos"]
    game.execute("MoveNE")
    pos = game.state()["player_pos"]
    assert pos["x"] == start["x"] + 1
    assert pos["y"] == start["y"] - 1


def test_message_log_welcome(game):
    """New game has at least one welcome message in the log."""
    s = game.state()
    msgs = s["messages"]
    assert len(msgs) >= 1, "New game should produce at least a welcome message"


def test_message_log_accumulates(game):
    """Successive actions add messages to the log."""
    s0 = game.state()
    count_before = len(s0["messages"])
    # Hit a wall to guarantee a message
    for _ in range(50):
        game.execute("MoveN")
    s1 = game.state()
    count_after = len(s1["messages"])
    assert count_after > count_before, "Wall bumps should add messages"


def test_message_log_max_length(game):
    """Message log does not grow beyond 7 visible entries."""
    # Generate many messages by bumping walls repeatedly
    for _ in range(20):
        game.execute("MoveN")
    s = game.state()
    msgs = s["messages"]
    assert len(msgs) <= 7, f"Message log should cap at 7 visible entries, got {len(msgs)}"


# ---------------------------------------------------------------------------
# Stats & Modifiers
# ---------------------------------------------------------------------------

def test_derived_max_mp(game):
    """max_mp = 5 + Lore * 4.  At base 10: 45."""
    s = game.state()
    assert s["derived"]["max_mp"] == 45


def test_derived_damage_mult(game):
    """damage_mult = 1.0 + 0.05 * Power.  At base 10: 1.5."""
    s = game.state()
    assert abs(s["derived"]["damage_mult"] - 1.5) < 0.01


def test_all_equipment_slots_reported(game):
    """State includes all 9 equipment slots, initially empty."""
    s = game.state()
    equip = s.get("equipment_slots", s.get("equipment", {}))
    assert len(equip) == 9
    expected = {"head", "body", "hands", "feet", "back", "amulet", "ring1", "ring2", "weapon"}
    reported = {slot.lower() for slot in equip.keys()}
    assert reported == expected


# ---------------------------------------------------------------------------
# Turn System & Enemies
# ---------------------------------------------------------------------------

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
