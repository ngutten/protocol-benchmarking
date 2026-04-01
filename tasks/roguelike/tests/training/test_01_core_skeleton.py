"""Training tests for Stage 1: Core Skeleton."""


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
