"""Holdout tests for Stage 6: Items, Inventory, Equipment.

These tests are NOT shown to the LLM during implementation.
They validate generalization beyond the training tests.
"""


def test_equip_modifies_stats(game):
    """Equipping the stealth cloak increases effective Mobility by 15."""
    stats_before = game.state()["stats"]["effective"][:]
    resp = game.create_item("stealth_cloak")
    cloak_id = resp.get("item_id")
    game.force_equip(cloak_id)
    stats_after = game.state()["stats"]["effective"][:]
    # Mobility is index 1; stealth_cloak adds +15 Mobility
    assert stats_after[1] == stats_before[1] + 15


def test_weight_tracking(game):
    """Picking up items increases carried weight."""
    game.create_item("iron_sword", x=5, y=5)
    game.execute("Pickup")
    s_after = game.state()
    assert "weight" in s_after or "carry_weight" in s_after


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

    # Try to add another item — should fail (capacity exceeded)
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
