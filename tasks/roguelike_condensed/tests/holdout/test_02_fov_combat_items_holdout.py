"""Holdout tests for Stage 2: FOV & Lighting, Combat & Status Effects, Items & Inventory.

These tests are NOT shown to the LLM during implementation.
They validate generalization beyond the training tests.
"""


# ---------------------------------------------------------------------------
# FOV & Lighting
# ---------------------------------------------------------------------------

def test_tile_memory(game):
    """Tiles become remembered after moving out of FOV range."""
    s = game.state()
    initial_visible = set(tuple(t) if isinstance(t, list) else (t["x"], t["y"])
                         for t in s["visible_tiles"])
    for _ in range(10):
        game.execute("MoveS")
    s2 = game.state()
    current_visible = set(tuple(t) if isinstance(t, list) else (t["x"], t["y"])
                          for t in s2["visible_tiles"])
    remembered = set(tuple(t) if isinstance(t, list) else (t["x"], t["y"])
                     for t in s2.get("remembered_tiles", []))
    # Tiles we could see before but can't now should be remembered
    left_fov = initial_visible - current_visible
    assert len(left_fov) > 0, "Moving 10 tiles south should leave some tiles out of FOV"
    assert left_fov.issubset(remembered), "Tiles that left FOV should be remembered"


def test_sound_detection(game):
    """Creature behind a wall within hearing range shows as heard."""
    # Build a wall between player (5,5) and skeleton at (5,2)
    game.set_tile(5, 4, "wall")
    game.set_tile(5, 3, "floor")
    game.set_tile(5, 2, "floor")
    eid = game.spawn_creature("skeleton", 5, 2)
    s = game.state()
    vis = s.get("creature_visibility", {})
    # Skeleton is 3 tiles away, behind a wall -- should be Heard (not Visible)
    eid_str = str(eid)
    entry = vis.get(eid_str, vis.get(eid, {}))
    if isinstance(entry, str):
        assert entry == "Heard"
    else:
        assert entry.get("state") == "Heard"


# ---------------------------------------------------------------------------
# Combat & Status Effects
# ---------------------------------------------------------------------------

def test_creature_death_message(game):
    """Killing a creature logs a death message."""
    eid = game.spawn_creature("goblin", 6, 5)
    game.set_hp(eid, 1)
    game.execute("MoveE")
    msgs = game.state()["messages"]
    assert any("die" in m.lower() or "kill" in m.lower() or "defeat" in m.lower()
               for m in msgs)


def test_player_death_grave_screen(game):
    """Player dying transitions to the Grave screen."""
    game.set_hp(0, 0)  # player HP to 0
    s = game.state()
    assert s.get("screen_mode") == "Grave" or s.get("player_dead", False)


def test_damage_has_variance(engine):
    """Multiple attacks with same setup produce different damage values."""
    damages = []
    for seed in range(10):
        engine.new_game(seed=seed)
        eid = engine.spawn_creature("goblin", 6, 5)
        hp_before = engine.get_entity(eid).get("hp", 50)
        engine.execute("MoveE")
        hp_after = engine.get_entity(eid).get("hp", 50)
        if hp_before is not None and hp_after is not None:
            damages.append(hp_before - hp_after)
    assert len(set(damages)) >= 2


def test_melee_attack_logs_message(game):
    """Attacking an enemy logs a hit message with damage amount."""
    eid = game.spawn_creature("goblin", 6, 5)
    game.execute("MoveE")  # bump-attack
    msgs = game.state()["messages"]
    assert any("hit" in m.lower() or "damage" in m.lower() or "attack" in m.lower()
               for m in msgs), \
        f"Melee attack should log a hit message. Messages: {msgs}"



# ---------------------------------------------------------------------------
# Items & Inventory
# ---------------------------------------------------------------------------

def test_equip_modifies_stats(game):
    """Equipping the stealth cloak increases effective Mobility by 15."""
    stats_before = game.state()["stats"]["effective"][:]
    resp = game.create_item("stealth_cloak")
    cloak_id = resp.get("item_id")
    game.force_equip(cloak_id)
    stats_after = game.state()["stats"]["effective"][:]
    # Mobility is index 1; stealth_cloak adds +15 Mobility
    assert stats_after[1] == stats_before[1] + 15


def test_put_item_in_container(game):
    """Items can be moved into a container via put_in_container."""
    pouch_resp = game.create_item("leather_pouch")
    pouch_id = pouch_resp.get("item_id")
    ring_resp = game.create_item("gold_ring")
    ring_id = ring_resp.get("item_id")

    resp = game.put_in_container(ring_id, pouch_id)
    assert resp.get("ok"), "put_in_container should succeed"

    contents = game.container_contents(pouch_id)
    content_ids = [item["id"] for item in contents]
    assert ring_id in content_ids, "Ring should be inside the pouch"


def test_take_item_from_container(game):
    """Items can be removed from a container via take_from_container."""
    pouch_resp = game.create_item("leather_pouch")
    pouch_id = pouch_resp.get("item_id")
    ring_resp = game.create_item("gold_ring")
    ring_id = ring_resp.get("item_id")

    game.put_in_container(ring_id, pouch_id)
    resp = game.take_from_container(ring_id, pouch_id)
    assert resp.get("ok"), "take_from_container should succeed"

    contents = game.container_contents(pouch_id)
    content_ids = [item["id"] for item in contents]
    assert ring_id not in content_ids, "Ring should no longer be in the pouch"


def test_container_capacity_enforced(game):
    """Cannot overfill a container beyond its capacity."""
    pouch_resp = game.create_item("leather_pouch")  # capacity 3.0
    pouch_id = pouch_resp.get("item_id")
    # Iron sword weighs 3.0, fill the pouch
    sword_resp = game.create_item("iron_sword")
    sword_id = sword_resp.get("item_id")
    game.put_in_container(sword_id, pouch_id)

    # Try to add another item -- should fail (capacity exceeded)
    ring_resp = game.create_item("gold_ring")  # weighs 0.1
    ring_id = ring_resp.get("item_id")
    resp = game.put_in_container(ring_id, pouch_id)
    # Either the response is not ok, or the ring is not in the container
    if resp.get("ok"):
        contents = game.container_contents(pouch_id)
        ids = [item["id"] for item in contents]
        assert ring_id not in ids, "Overfilling should be rejected"
    else:
        assert "fit" in resp.get("error", "").lower() or not resp.get("ok")


def test_container_no_nesting(game):
    """Containers cannot be put inside other containers."""
    pouch1_resp = game.create_item("leather_pouch")
    pouch1_id = pouch1_resp.get("item_id")
    pouch2_resp = game.create_item("leather_pouch")
    pouch2_id = pouch2_resp.get("item_id")

    resp = game.put_in_container(pouch2_id, pouch1_id)
    # Should fail
    if resp.get("ok"):
        contents = game.container_contents(pouch1_id)
        ids = [item["id"] for item in contents]
        assert pouch2_id not in ids, "Container nesting should be rejected"
    else:
        assert not resp.get("ok")
