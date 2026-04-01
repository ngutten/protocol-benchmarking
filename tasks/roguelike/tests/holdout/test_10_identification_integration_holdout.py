"""Holdout tests for Stage 10: Identification System Polish, Integration.

These tests are NOT shown to the LLM during implementation.
They validate generalization beyond the training tests.
"""


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
