"""Training tests for Stage 4: FOV, Lighting, Map Memory."""


def test_visible_tiles_present(game):
    """Player's FOV respects walls placed around them."""
    # Place walls to create a known FOV boundary
    game.set_tile(7, 5, "wall")   # wall 2 tiles east of player at (5,5)
    game.set_tile(5, 3, "wall")   # wall 2 tiles north
    s = game.state()
    visible = s["visible_tiles"]
    vis_set = set(tuple(t) if isinstance(t, list) else (t["x"], t["y"])
                  for t in visible)
    # Player's own tile is visible
    assert (5, 5) in vis_set
    # Tile between player and wall is visible
    assert (6, 5) in vis_set
    # Tile behind the east wall should not be visible
    assert (8, 5) not in vis_set


def test_player_position_visible(game):
    """Player's own tile is always visible."""
    s = game.state()
    pos = s["player_pos"]
    visible = s["visible_tiles"]
    assert [pos["x"], pos["y"]] in visible or {"x": pos["x"], "y": pos["y"]} in visible


def test_remembered_tiles_initially_empty(game):
    """Before moving, remembered_tiles list is empty or absent."""
    s = game.state()
    remembered = s.get("remembered_tiles", [])
    assert len(remembered) == 0
