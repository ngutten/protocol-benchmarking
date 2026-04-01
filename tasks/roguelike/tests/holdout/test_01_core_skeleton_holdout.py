"""Holdout tests for Stage 1: Core Skeleton.

These tests are NOT shown to the LLM during implementation.
They validate generalization beyond the training tests.
"""


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
