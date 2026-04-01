"""Training tests for Stage 6: Items, Inventory, Equipment."""


def test_inventory_in_state(game):
    """Creating items in inventory populates the inventory list."""
    game.create_item("iron_sword")   # no x,y → directly in inventory
    game.create_item("gold_ring")
    s = game.state()
    inv = s["inventory"]
    assert len(inv) >= 2
    names = [item["name"].lower() for item in inv]
    assert any("sword" in n for n in names)
    assert any("ring" in n for n in names)


def test_create_item_on_ground(game):
    """Creating an item at a position places it on the ground."""
    resp = game.create_item("healing_potion", x=5, y=5)
    assert resp.get("ok")
    s = game.state()
    ground = s.get("ground_items", [])
    assert len(ground) > 0


def test_pickup_item(game):
    """Player can pick up items from their tile."""
    game.create_item("healing_potion", x=5, y=5)
    game.execute("Pickup")  # 'g' key
    s = game.state()
    assert len(s["inventory"]) > 0
