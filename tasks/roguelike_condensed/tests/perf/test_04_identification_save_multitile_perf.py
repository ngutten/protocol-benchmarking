"""Performance benchmarks for Stage 4: Identification & Integration, Save/Load, Multi-Tile Creatures."""
import time


# ---------------------------------------------------------------------------
# Identification & Integration
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Save / Load
# ---------------------------------------------------------------------------

class TestSaveLoadThroughput:
    """Measure save and load cycle time."""

    def _build_complex_state(self, game):
        """Set up a non-trivial game state for save/load benchmarking."""
        for template in ["iron_sword", "iron_helmet", "leather_armor",
                         "speed_boots", "ring_of_light"]:
            resp = game.create_item(template)
            item_id = resp.get("item_id")
            if item_id is not None:
                game.force_equip(item_id)
        for _ in range(20):
            game.create_item("healing_potion")
        for ab in ["leaping_strike", "magic_missile", "sleep"]:
            game.learn_ability(ab)
        s = game.state()
        w = s["map"]["width"]
        h = s["map"]["height"]
        for i in range(8):
            x = 2 + (i * 3) % (w - 4)
            y = 2 + (i * 5) % (h - 4)
            game.spawn_creature("goblin", x, y)

    def test_save_10_times(self, game):
        """Save game state 10 times with a loaded game."""
        self._build_complex_state(game)
        start = time.perf_counter()
        for _ in range(10):
            game.save_game()
        elapsed = time.perf_counter() - start
        print(f'{{"bench_metric": "ops_per_second", "test": "test_save_10_times", '
              f'"value": {10 / elapsed:.2f}, "iterations": 10, '
              f'"duration_seconds": {elapsed:.6f}}}')

    def test_save_load_cycle_10(self, game):
        """Save then load 10 times."""
        self._build_complex_state(game)
        resp = game.save_game()
        path = resp.get("path", "")
        if not path:
            return
        start = time.perf_counter()
        for _ in range(10):
            game.save_game(path)
            game.load_game(path)
        elapsed = time.perf_counter() - start
        print(f'{{"bench_metric": "ops_per_second", "test": "test_save_load_cycle_10", '
              f'"value": {10 / elapsed:.2f}, "iterations": 10, '
              f'"duration_seconds": {elapsed:.6f}}}')


class TestSaveWithMultipleLevels:
    """Measure save/load time with multiple generated levels."""

    def test_save_load_with_5_levels(self, game):
        """Generate 5 levels, save/load 5 times."""
        for depth in range(1, 6):
            game.set_level(depth)
        resp = game.save_game()
        path = resp.get("path", "")
        if not path:
            return
        start = time.perf_counter()
        for _ in range(5):
            game.save_game(path)
            game.load_game(path)
        elapsed = time.perf_counter() - start
        print(f'{{"bench_metric": "ops_per_second", "test": "test_save_load_with_5_levels", '
              f'"value": {5 / elapsed:.2f}, "iterations": 5, "levels": 5, '
              f'"duration_seconds": {elapsed:.6f}}}')


# ---------------------------------------------------------------------------
# Multi-Tile Creatures
# ---------------------------------------------------------------------------

class TestMultiTileEnemyPhase:
    """Measure enemy phase processing with multi-tile creatures."""

    def test_enemy_phase_5_ogres(self, game):
        """Force 30 enemy phases with 5 multi-tile (2x2) ogres."""
        s = game.state()
        w = s["map"]["width"]
        h = s["map"]["height"]
        spawned = 0
        for i in range(5):
            x = 3 + (i * 6) % (w - 6)
            y = 3 + (i * 7) % (h - 6)
            eid = game.spawn_creature("ogre", x, y, size={"w": 2, "h": 2})
            if eid is not None:
                spawned += 1
        start = time.perf_counter()
        for _ in range(30):
            game.force_enemy_phase()
        elapsed = time.perf_counter() - start
        print(f'{{"bench_metric": "ops_per_second", "test": "test_enemy_phase_5_ogres", '
              f'"value": {30 / elapsed:.2f}, "iterations": 30, "ogres": {spawned}, '
              f'"duration_seconds": {elapsed:.6f}}}')


class TestMultiTilePathfinding:
    """Measure pathfinding cost for multi-tile creatures."""

    def test_mixed_enemies_phase(self, game):
        """Force 30 enemy phases with a mix of 1x1 and 2x2 creatures."""
        s = game.state()
        w = s["map"]["width"]
        h = s["map"]["height"]
        for i in range(5):
            x = 2 + (i * 3) % (w - 4)
            y = 2 + (i * 5) % (h - 4)
            game.spawn_creature("goblin", x, y)
        for i in range(3):
            x = 4 + (i * 7) % (w - 6)
            y = 4 + (i * 9) % (h - 6)
            game.spawn_creature("ogre", x, y, size={"w": 2, "h": 2})
        start = time.perf_counter()
        for _ in range(30):
            game.force_enemy_phase()
        elapsed = time.perf_counter() - start
        print(f'{{"bench_metric": "ops_per_second", "test": "test_mixed_enemies_phase", '
              f'"value": {30 / elapsed:.2f}, "iterations": 30, '
              f'"duration_seconds": {elapsed:.6f}}}')


class TestMultiTileStateQuery:
    """Measure state query overhead with multi-tile entity data."""

    def test_state_with_multi_tile_entities(self, game):
        """Query state 100 times with multi-tile creatures present."""
        s = game.state()
        w = s["map"]["width"]
        h = s["map"]["height"]
        for i in range(4):
            x = 4 + (i * 8) % (w - 6)
            y = 4 + (i * 8) % (h - 6)
            game.spawn_creature("ogre", x, y, size={"w": 2, "h": 2})
        start = time.perf_counter()
        for _ in range(100):
            game.state()
        elapsed = time.perf_counter() - start
        print(f'{{"bench_metric": "ops_per_second", "test": "test_state_with_multi_tile_entities", '
              f'"value": {100 / elapsed:.2f}, "iterations": 100, '
              f'"duration_seconds": {elapsed:.6f}}}')
