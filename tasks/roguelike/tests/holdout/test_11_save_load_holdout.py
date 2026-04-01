"""Holdout tests for Stage 11: Save / Load System.

These tests are NOT shown to the LLM during implementation.
They validate generalization beyond the training tests.
"""
import os
import tempfile


def test_rng_state_preserved(engine):
    """RNG state continues correctly from a save point."""
    engine.new_game(seed=42)
    for _ in range(5):
        engine.execute("MoveE")

    with tempfile.TemporaryDirectory() as tmpdir:
        path = os.path.join(tmpdir, "test.sav")
        engine.save_game(path=path)

        engine.execute("MoveE")
        s1 = engine.state()

        engine.load_game(path=path)
        engine.execute("MoveE")
        s2 = engine.state()

    assert s1["player_pos"] == s2["player_pos"]


def test_player_death_archives_save(game):
    """On player death, save file is archived (renamed, not deleted)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        path = os.path.join(tmpdir, "test.sav")
        game.save_game(path=path)
        assert os.path.isfile(path)
        # Kill the player
        game.set_hp(0, 0)
        # Save should be archived: original renamed to a dead_* file
        files = os.listdir(tmpdir)
        assert any(f != "test.sav" for f in files), \
            "Save should be archived with a new name on death"


def test_container_contents_survive_save_load(game):
    """Items inside a container are preserved across save/load."""
    pouch_resp = game.create_item("leather_pouch")
    pouch_id = pouch_resp.get("item_id")
    ring_resp = game.create_item("gold_ring")
    ring_id = ring_resp.get("item_id")
    game.put_in_container(ring_id, pouch_id)

    # Verify ring is in pouch before save
    contents_before = game.container_contents(pouch_id)
    assert any(item["id"] == ring_id for item in contents_before)

    with tempfile.TemporaryDirectory() as tmpdir:
        path = os.path.join(tmpdir, "test.sav")
        game.save_game(path=path)
        game.new_game(seed=999)  # start a different game
        game.load_game(path=path)

        # After load, check container contents are intact
        contents_after = game.container_contents(pouch_id)
        content_ids = [item["id"] for item in contents_after]
        assert ring_id in content_ids, \
            "Container contents should survive save/load"
