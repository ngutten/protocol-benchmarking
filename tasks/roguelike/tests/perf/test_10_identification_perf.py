"""Performance benchmarks for Stage 10: Identification & Integration."""
import time


class TestFullyLoadedStateQuery:
    """Measure state query speed with all systems active."""

    def test_complex_state_query_100(self, game):
        """Load up the game with items, abilities, enemies, then query state 100 times."""
        # Equip gear
        for template in ["iron_sword", "iron_helmet", "leather_armor",
                         "leather_gloves", "speed_boots", "ring_of_light"]:
            resp = game.create_item(template)
            item_id = resp.get("item_id")
            if item_id is not None:
                game.force_equip(item_id)
        # Add inventory items
        for _ in range(20):
            game.create_item("healing_potion")
        # Learn abilities
        for ab in ["leaping_strike", "magic_missile", "sleep"]:
            game.learn_ability(ab)
        # Spawn enemies
        s = game.state()
        w = s["map"]["width"]
        h = s["map"]["height"]
        for i in range(10):
            x = 2 + (i * 3) % (w - 4)
            y = 2 + (i * 5) % (h - 4)
            game.spawn_creature("goblin", x, y)
        # Apply status effects
        game.apply_status(0, "Regen", duration_mp=50000, magnitude=2)
        game.apply_status(0, "Haste", duration_mp=50000, magnitude=10)

        start = time.perf_counter()
        for _ in range(100):
            game.state()
        elapsed = time.perf_counter() - start
        print(f'{{"bench_metric": "ops_per_second", "test": "test_complex_state_query_100", '
              f'"value": {100 / elapsed:.2f}, "iterations": 100, '
              f'"duration_seconds": {elapsed:.6f}}}')


class TestEquipModifierChurn:
    """Measure modifier stack performance under equipment cycling."""

    def test_equip_cycle_with_stats_query(self, game):
        """Equip 6 items, query state, repeat 30 times."""
        items = []
        for template in ["iron_sword", "iron_helmet", "leather_armor",
                         "speed_boots", "ring_of_light", "stealth_cloak"]:
            resp = game.create_item(template)
            item_id = resp.get("item_id")
            if item_id is not None:
                items.append(item_id)
        start = time.perf_counter()
        for _ in range(30):
            for item_id in items:
                game.force_equip(item_id)
            game.state()
        elapsed = time.perf_counter() - start
        print(f'{{"bench_metric": "ops_per_second", "test": "test_equip_cycle_with_stats_query", '
              f'"value": {30 / elapsed:.2f}, "iterations": 30, "items": {len(items)}, '
              f'"duration_seconds": {elapsed:.6f}}}')
