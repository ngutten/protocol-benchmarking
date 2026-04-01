"""Performance benchmarks for Stage 2: FOV & Lighting, Combat & Status Effects, Items & Inventory."""
import time


# ---------------------------------------------------------------------------
# FOV & Lighting
# ---------------------------------------------------------------------------

class TestFOVComputationThroughput:
    """Measure FOV recomputation cost after movement."""

    def test_fov_complex_map_movement_200(self, game):
        """200 moves on a map with interior walls that create complex FOV geometry."""
        s = game.state()
        w = s["map"]["width"]
        h = s["map"]["height"]
        for col in range(4, w - 4, 4):
            gap = (col * 3) % (h - 6) + 3
            for row in range(2, h - 2):
                if row != gap:
                    game.set_tile(col, row, "wall")
        game.move_to(3, h // 2)
        directions = ["MoveE", "MoveW"]
        start = time.perf_counter()
        for i in range(200):
            game.execute(directions[i % 2])
            game.state()
        elapsed = time.perf_counter() - start
        print(f'{{"bench_metric": "ops_per_second", "test": "test_fov_complex_map_movement_200", '
              f'"value": {200 / elapsed:.2f}, "iterations": 200, '
              f'"duration_seconds": {elapsed:.6f}}}')

    def test_fov_after_movement_200(self, game):
        """200 moves that each trigger FOV recomputation."""
        directions = ["MoveE", "MoveW"]
        start = time.perf_counter()
        for i in range(200):
            game.execute(directions[i % 2])
            game.state()
        elapsed = time.perf_counter() - start
        print(f'{{"bench_metric": "ops_per_second", "test": "test_fov_after_movement_200", '
              f'"value": {200 / elapsed:.2f}, "iterations": 200, '
              f'"duration_seconds": {elapsed:.6f}}}')


class TestFOVWithEnemies:
    """FOV computation with enemies that also compute FOV each turn."""

    def test_fov_with_10_enemies(self, game):
        """50 enemy phases where each enemy also computes FOV for detection."""
        s = game.state()
        w = s["map"]["width"]
        h = s["map"]["height"]
        for i in range(10):
            x = 2 + (i * 3) % (w - 4)
            y = 2 + (i * 5) % (h - 4)
            game.spawn_creature("goblin", x, y)
        start = time.perf_counter()
        for _ in range(50):
            game.force_enemy_phase()
        elapsed = time.perf_counter() - start
        print(f'{{"bench_metric": "ops_per_second", "test": "test_fov_with_10_enemies", '
              f'"value": {50 / elapsed:.2f}, "iterations": 50, "enemies": 10, '
              f'"duration_seconds": {elapsed:.6f}}}')


# ---------------------------------------------------------------------------
# Combat & Status Effects
# ---------------------------------------------------------------------------

class TestCombatThroughput:
    """Measure combat resolution speed via bump attacks."""

    def test_melee_attack_50(self, game):
        """Spawn a tough enemy and bump-attack it 50 times."""
        s = game.state()
        px, py = s["player_pos"]["x"], s["player_pos"]["y"]
        eid = game.spawn_creature("skeleton", px + 1, py)
        if eid is not None:
            game.set_hp(eid, 99999)
        start = time.perf_counter()
        for _ in range(50):
            game.execute("MoveE")
        elapsed = time.perf_counter() - start
        print(f'{{"bench_metric": "ops_per_second", "test": "test_melee_attack_50", '
              f'"value": {50 / elapsed:.2f}, "iterations": 50, '
              f'"duration_seconds": {elapsed:.6f}}}')


class TestStatusEffectThroughput:
    """Measure status effect application and ticking."""

    def test_apply_status_100(self, game):
        """Apply 100 status effects to the player."""
        statuses = ["Poison", "Slow", "Regen", "Haste"]
        start = time.perf_counter()
        for i in range(100):
            game.apply_status(0, statuses[i % len(statuses)],
                              duration_mp=500, magnitude=1)
        elapsed = time.perf_counter() - start
        print(f'{{"bench_metric": "ops_per_second", "test": "test_apply_status_100", '
              f'"value": {100 / elapsed:.2f}, "iterations": 100, '
              f'"duration_seconds": {elapsed:.6f}}}')

    def test_status_tick_via_movement(self, game):
        """Apply several effects then move 200 times to tick them."""
        game.apply_status(0, "Poison", duration_mp=50000, magnitude=1)
        game.apply_status(0, "Regen", duration_mp=50000, magnitude=2)
        game.apply_status(0, "Haste", duration_mp=50000, magnitude=10)
        game.set_hp(0, 99999)
        directions = ["MoveE", "MoveW"]
        start = time.perf_counter()
        for i in range(200):
            game.execute(directions[i % 2])
        elapsed = time.perf_counter() - start
        print(f'{{"bench_metric": "ops_per_second", "test": "test_status_tick_via_movement", '
              f'"value": {200 / elapsed:.2f}, "iterations": 200, '
              f'"duration_seconds": {elapsed:.6f}}}')


# ---------------------------------------------------------------------------
# Items & Inventory
# ---------------------------------------------------------------------------

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
