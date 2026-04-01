"""Training tests for Stage 7: Abilities, Ability Screen, Martial & Spell System."""


def test_learn_ability(game):
    """Learning an ability adds it to the abilities list."""
    game.learn_ability("magic_missile")
    s = game.state()
    abilities = s.get("abilities", [])
    assert any(a["name"] == "magic_missile" or "magic_missile" in a.get("name", "").lower()
               for a in abilities)


def test_abilities_in_state(game):
    """Learning magic_missile populates abilities with correct fields."""
    game.learn_ability("magic_missile")
    s = game.state()
    abilities = s["abilities"]
    assert len(abilities) >= 1
    mm = next(a for a in abilities if a["name"] == "magic_missile")
    assert "bound_key" in mm
    assert "mp_cost" in mm
    assert mm["mp_cost"] == 8


def test_ability_slot_limit(game):
    """Cannot learn more abilities than available slots allow."""
    s = game.state()
    max_slots = s["derived"].get("ability_slots", 5)
    # Use the three spec-defined abilities (each costs 1 slot)
    for name in ["magic_missile", "leaping_strike", "sleep"]:
        game.learn_ability(name)
    s = game.state()
    learned = len(s.get("abilities", []))
    assert learned <= max_slots
    assert learned == min(3, max_slots)
