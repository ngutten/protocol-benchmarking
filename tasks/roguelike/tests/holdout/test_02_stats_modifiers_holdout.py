"""Holdout tests for Stage 2: Stats, Modifier Stack, Stat Panel, Leveling.

These tests are NOT shown to the LLM during implementation.
They validate generalization beyond the training tests.
"""


def test_derived_max_mp(game):
    """max_mp = 5 + Lore * 4.  At base 10: 45."""
    s = game.state()
    assert s["derived"]["max_mp"] == 45


def test_derived_damage_mult(game):
    """damage_mult = 1.0 + 0.05 * Power.  At base 10: 1.5."""
    s = game.state()
    assert abs(s["derived"]["damage_mult"] - 1.5) < 0.01


def test_all_equipment_slots_reported(game):
    """State includes all 9 equipment slots, initially empty."""
    s = game.state()
    equip = s.get("equipment_slots", s.get("equipment", {}))
    assert len(equip) == 9
    expected = {"head", "body", "hands", "feet", "back", "amulet", "ring1", "ring2", "weapon"}
    reported = {slot.lower() for slot in equip.keys()}
    assert reported == expected
