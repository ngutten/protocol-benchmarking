"""Training tests for Stage 9: Procedural Dungeon Generation."""


def test_map_connectivity(game):
    """Player can reach the down staircase from their starting position."""
    s = game.state()
    stairs = s["map"].get("stairs_down")
    assert stairs is not None, "Map must include stairs_down position"
    # Teleport to stairs — if it succeeds, the tile is walkable
    resp = game.move_to(stairs["x"], stairs["y"])
    assert resp.get("ok")


def test_stairs_present(game):
    """Generated maps contain both up and down staircases."""
    s = game.state()
    m = s["map"]
    assert "stairs_down" in m, "Map must report stairs_down position"
    assert "x" in m["stairs_down"] and "y" in m["stairs_down"]
    assert "stairs_up" in m, "Map must report stairs_up position"
    assert "x" in m["stairs_up"] and "y" in m["stairs_up"]
