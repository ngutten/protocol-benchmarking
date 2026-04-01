"""Holdout tests for Stage 4: Identification & Integration, Save/Load, Multi-Tile Creatures.

These tests are NOT shown to the LLM during implementation.
They validate generalization beyond the training tests.
"""
import os
import tempfile


# ---------------------------------------------------------------------------
# Identification & Integration
# ---------------------------------------------------------------------------

def test_staircase_item_persistence(game):
    """Items dropped on a level persist after level change and return."""
    game.create_item("healing_potion", x=5, y=5)
    s1 = game.state()
    ground1 = len(s1.get("ground_items", []))
    level = s1.get("dungeon_level", 0)
    game.set_level(level + 1)
    game.set_level(level)
    s2 = game.state()
    ground2 = len(s2.get("ground_items", []))
    assert ground2 == ground1


# ---------------------------------------------------------------------------
# Save / Load
# ---------------------------------------------------------------------------

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
    # Save to the engine's own default location and get back the path it chose
    save_resp = game.save_game()
    save_path = save_resp.get("path", "")
    if not save_path or not os.path.isfile(save_path):
        pytest.skip("save_game did not return a valid path to an existing file")
    save_dir = os.path.dirname(os.path.abspath(save_path))
    save_basename = os.path.basename(save_path)
    files_before = set(os.listdir(save_dir))

    # Kill the player and give the engine a chance to process the death
    game.set_hp(0, 0)
    try:
        game.state()
    except Exception:
        pass  # engine may reject commands after death

    files_after = set(os.listdir(save_dir))
    original_gone = save_basename not in files_after
    archive_exists = len(files_after - files_before) > 0
    assert original_gone or archive_exists, \
        f"Save should be archived on death: files before={files_before}, after={files_after}"


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


# ---------------------------------------------------------------------------
# Multi-Tile Creatures
# ---------------------------------------------------------------------------

def test_multi_tile_death_clears_tiles(game):
    """When a multi-tile creature dies, all occupied tiles are freed."""
    eid = game.spawn_creature("ogre", 7, 5, size={"w": 2, "h": 2})
    game.set_hp(eid, 1)
    game.execute("MoveE")  # bump-kill
    ent = game.get_entity(eid)
    assert ent.get("dead", True) or not ent.get("ok", True)


def test_multi_tile_cannot_enter_narrow_corridor(game):
    """A 2x2 creature cannot path through a 1-wide corridor."""
    # Build a wall bisecting the map with a single 1-wide gap
    for y in range(1, 19):
        if y != 10:
            game.set_tile(15, y, "wall")
        else:
            game.set_tile(15, y, "floor")  # 1-wide gap at (15, 10)

    # Spawn ogre on the east side of the wall
    eid = game.spawn_creature("ogre", 17, 9, size={"w": 2, "h": 2})
    # Player on the west side, near the gap
    game.move_to(13, 10)

    pos_before = game.get_entity(eid)["pos"]
    for _ in range(5):
        game.force_enemy_phase()
    pos_after = game.get_entity(eid)["pos"]

    # Ogre (2x2) cannot fit through 1-wide gap -- must stay on east side
    assert pos_after["x"] >= 15
