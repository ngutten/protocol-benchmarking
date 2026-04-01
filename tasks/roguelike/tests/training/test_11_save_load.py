"""Training tests for Stage 11: Save / Load System."""
import os
import tempfile


def test_save_creates_file(game):
    """Saving the game creates a save file."""
    with tempfile.TemporaryDirectory() as tmpdir:
        path = os.path.join(tmpdir, "test.sav")
        resp = game.save_game(path=path)
        assert resp.get("ok")
        assert os.path.isfile(path)


def test_save_load_roundtrip(game):
    """State is preserved across save/load."""
    game.execute("MoveE")
    game.execute("MoveE")
    s_before = game.state()

    with tempfile.TemporaryDirectory() as tmpdir:
        path = os.path.join(tmpdir, "test.sav")
        game.save_game(path=path)
        game.new_game(seed=999)
        game.load_game(path=path)
        s_after = game.state()

    assert s_after["player_pos"] == s_before["player_pos"]
    assert s_after["seed"] == s_before["seed"]
