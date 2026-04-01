"""Holdout tests for Stage 8: Ranged Combat, Targeting Interface.

These tests are NOT shown to the LLM during implementation.
They validate generalization beyond the training tests.
"""


def test_ranged_accuracy_decreases_with_distance(game):
    """Accuracy is lower for far targets than close targets."""
    resp = game.create_item("shortbow")
    bow_id = resp.get("item_id")
    game.force_equip(bow_id)
    # Close target within Perception/2 (base Perc=10, so within 5 tiles)
    game.spawn_creature("goblin", 8, 5)    # distance 3
    # Far target beyond Perception/2
    game.spawn_creature("goblin", 12, 5)   # distance 7
    game.execute("Fire")
    # Cycle through targets and record hit_chance for each
    accuracies = []
    for _ in range(2):
        game.execute("Tab")
        s = game.state()
        accuracies.append(s["targeting"]["hit_chance"])
    game.execute("Cancel")
    assert min(accuracies) < max(accuracies)
    assert max(accuracies) >= 90   # close target should be near base 95%


def test_escape_cancels_targeting(game):
    """Pressing Escape exits targeting mode without firing."""
    resp = game.create_item("shortbow")
    bow_id = resp.get("item_id")
    game.force_equip(bow_id)
    game.execute("Fire")
    game.execute("Cancel")  # Escape
    s = game.state()
    assert s.get("screen_mode") != "Targeting"
