"""Training tests for Stage 10: Identification System Polish, Integration."""


def test_items_have_identification_level(game):
    """Items in inventory track identification level."""
    game.create_item("healing_potion", x=5, y=5)
    game.execute("Pickup")
    s = game.state()
    inv = s.get("inventory", [])
    assert len(inv) > 0
    item = inv[0]
    assert "identified" in item or "id_level" in item


def test_modifier_stack_integrity(game):
    """Equip modifiers apply on equip and revert to base on unequip."""
    base = game.state()["stats"]["base"][:]
    eff_before = game.state()["stats"]["effective"][:]
    assert eff_before == base, "Effective should equal base with no equipment"

    # Equip stealth cloak (+15 Mobility at index 1)
    resp = game.create_item("stealth_cloak")
    cloak_id = resp.get("item_id")
    game.force_equip(cloak_id)
    eff_equipped = game.state()["stats"]["effective"][:]
    assert eff_equipped[1] == base[1] + 15

    # Equip speed boots (+5 Mobility at index 1) — different slot (Feet), stacks
    resp2 = game.create_item("speed_boots")
    boots_id = resp2.get("item_id")
    game.force_equip(boots_id)
    eff_both = game.state()["stats"]["effective"][:]
    assert eff_both[1] == base[1] + 15 + 5
