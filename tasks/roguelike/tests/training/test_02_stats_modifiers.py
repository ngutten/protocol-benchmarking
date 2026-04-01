"""Training tests for Stage 2: Stats, Modifier Stack, Stat Panel, Leveling."""


def test_base_stats_present(game):
    """State includes base stats array for all 6 stats."""
    s = game.state()
    assert "stats" in s
    base = s["stats"]["base"]
    assert len(base) == 6


def test_derived_max_hp(game):
    """max_hp = 20 + Toughness * 8.  At base 10: 100."""
    s = game.state()
    assert s["derived"]["max_hp"] == 100


def test_effective_equals_base_without_modifiers(game):
    """Without modifiers, effective stats equal base stats."""
    s = game.state()
    base_power = s["stats"]["base"][0]  # Power is index 0
    eff_power = s["stats"]["effective"][0]
    assert eff_power == base_power


def test_level_up_grants_points(game):
    """Setting XP to level threshold enables level-up with 2 points."""
    game.set_xp(100)
    s = game.state()
    assert s["level_info"]["pending_points"] == 2
