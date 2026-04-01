"""Performance benchmarks for Stage 6: Items & Inventory."""
import time


class TestItemCreationThroughput:
    """Measure item creation and inventory management speed."""

    def test_create_100_items(self, game):
        """Create 100 items in the player inventory."""
        templates = ["healing_potion", "iron_sword", "iron_helmet", "leather_armor",
                     "gold_ring", "leather_gloves"]
        start = time.perf_counter()
        for i in range(100):
            game.create_item(templates[i % len(templates)])
        elapsed = time.perf_counter() - start
        print(f'{{"bench_metric": "ops_per_second", "test": "test_create_100_items", '
              f'"value": {100 / elapsed:.2f}, "iterations": 100, '
              f'"duration_seconds": {elapsed:.6f}}}')

    def test_create_50_ground_items(self, game):
        """Create 50 items scattered on the ground."""
        s = game.state()
        w = s["map"]["width"]
        h = s["map"]["height"]
        start = time.perf_counter()
        for i in range(50):
            x = 2 + (i * 3) % (w - 4)
            y = 2 + (i * 5) % (h - 4)
            game.create_item("healing_potion", x, y)
        elapsed = time.perf_counter() - start
        print(f'{{"bench_metric": "ops_per_second", "test": "test_create_50_ground_items", '
              f'"value": {50 / elapsed:.2f}, "iterations": 50, '
              f'"duration_seconds": {elapsed:.6f}}}')


class TestInventoryStateQuery:
    """Measure state query speed with a loaded inventory."""

    def test_state_with_50_items(self, game):
        """Query state 200 times with 50 items in inventory."""
        for i in range(50):
            game.create_item("healing_potion")
        start = time.perf_counter()
        for _ in range(200):
            game.state()
        elapsed = time.perf_counter() - start
        print(f'{{"bench_metric": "ops_per_second", "test": "test_state_with_50_items", '
              f'"value": {200 / elapsed:.2f}, "iterations": 200, "inventory_size": 50, '
              f'"duration_seconds": {elapsed:.6f}}}')


class TestEquipUnequipThroughput:
    """Measure equipment cycling speed (modifier stack churn)."""

    def test_equip_swap_cycle_50(self, game):
        """Create two weapons, alternate equipping them to force modifier stack changes."""
        resp_a = game.create_item("iron_sword")
        resp_b = game.create_item("shortbow")
        id_a = resp_a.get("item_id")
        id_b = resp_b.get("item_id")
        if id_a is None or id_b is None:
            return
        items = [id_a, id_b]
        start = time.perf_counter()
        for i in range(50):
            game.force_equip(items[i % 2])
            game.state()
        elapsed = time.perf_counter() - start
        print(f'{{"bench_metric": "ops_per_second", "test": "test_equip_swap_cycle_50", '
              f'"value": {50 / elapsed:.2f}, "iterations": 50, '
              f'"duration_seconds": {elapsed:.6f}}}')
