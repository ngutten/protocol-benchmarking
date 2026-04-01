"""Performance benchmarks for Stage 3: Abilities, Ranged Combat & Targeting, Procedural Generation."""
import time


# ---------------------------------------------------------------------------
# Abilities
# ---------------------------------------------------------------------------

class TestAbilityCombatThroughput:
    """Measure combat throughput with the ability system active."""

    def test_melee_with_abilities_50(self, game):
        """Bump-attack an enemy 50 times with all abilities learned."""
        for ab in ["leaping_strike", "magic_missile", "sleep"]:
            game.learn_ability(ab)
        s = game.state()
        px, py = s["player_pos"]["x"], s["player_pos"]["y"]
        eid = game.spawn_creature("skeleton", px + 1, py)
        if eid is not None:
            game.set_hp(eid, 99999)
        start = time.perf_counter()
        for _ in range(50):
            game.execute("MoveE")
        elapsed = time.perf_counter() - start
        print(f'{{"bench_metric": "ops_per_second", "test": "test_melee_with_abilities_50", '
              f'"value": {50 / elapsed:.2f}, "iterations": 50, '
              f'"duration_seconds": {elapsed:.6f}}}')


class TestAbilityEnemyPhaseThroughput:
    """Measure enemy phase throughput with ability system active."""

    def test_enemy_phase_with_abilities_50(self, game):
        """Force 50 enemy phases with abilities learned and enemies present."""
        for ab in ["leaping_strike", "magic_missile", "sleep"]:
            game.learn_ability(ab)
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
        print(f'{{"bench_metric": "ops_per_second", "test": "test_enemy_phase_with_abilities_50", '
              f'"value": {50 / elapsed:.2f}, "iterations": 50, "enemies": 10, '
              f'"duration_seconds": {elapsed:.6f}}}')


# ---------------------------------------------------------------------------
# Ranged Combat & Targeting
# ---------------------------------------------------------------------------

class TestTargetingModeThroughput:
    """Measure targeting mode entry/exit which computes valid targets and LOS."""

    def test_targeting_enter_exit_100(self, game):
        """Enter and exit targeting mode 100 times with 15 enemies on map."""
        resp = game.create_item("shortbow")
        item_id = resp.get("item_id")
        if item_id is not None:
            game.force_equip(item_id)
        s = game.state()
        w = s["map"]["width"]
        h = s["map"]["height"]
        for i in range(15):
            x = 2 + (i * 3) % (w - 4)
            y = 2 + (i * 5) % (h - 4)
            game.spawn_creature("goblin", x, y)
        start = time.perf_counter()
        for _ in range(100):
            game.execute("Fire")
            game.execute("Cancel")
        elapsed = time.perf_counter() - start
        print(f'{{"bench_metric": "ops_per_second", "test": "test_targeting_enter_exit_100", '
              f'"value": {100 / elapsed:.2f}, "iterations": 100, "enemies": 15, '
              f'"duration_seconds": {elapsed:.6f}}}')


class TestRangedCombatThroughput:
    """Measure ranged combat resolution speed."""

    def test_fire_action_50(self, game):
        """Equip a bow, spawn a target, and fire 50 times."""
        resp = game.create_item("shortbow")
        item_id = resp.get("item_id")
        if item_id is not None:
            game.force_equip(item_id)
        s = game.state()
        px, py = s["player_pos"]["x"], s["player_pos"]["y"]
        eid = game.spawn_creature("skeleton", px + 4, py)
        if eid is not None:
            game.set_hp(eid, 99999)
        start = time.perf_counter()
        for _ in range(50):
            game.execute("Fire")
            game.execute("Confirm")
        elapsed = time.perf_counter() - start
        print(f'{{"bench_metric": "ops_per_second", "test": "test_fire_action_50", '
              f'"value": {50 / elapsed:.2f}, "iterations": 50, '
              f'"duration_seconds": {elapsed:.6f}}}')


# ---------------------------------------------------------------------------
# Procedural Generation
# ---------------------------------------------------------------------------

class TestLevelGenerationThroughput:
    """Measure dungeon level generation speed."""

    def test_generate_10_levels(self, game):
        """Generate 10 dungeon levels sequentially."""
        start = time.perf_counter()
        for depth in range(1, 11):
            game.set_level(depth)
        elapsed = time.perf_counter() - start
        print(f'{{"bench_metric": "level_gen_time_seconds", "test": "test_generate_10_levels", '
              f'"value": {elapsed:.6f}, "iterations": 10, '
              f'"duration_seconds": {elapsed:.6f}}}')

    def test_generate_level_and_query_state(self, game):
        """Generate a level then query its full state (map + entities)."""
        start = time.perf_counter()
        for depth in range(1, 6):
            game.set_level(depth)
            game.state()
        elapsed = time.perf_counter() - start
        print(f'{{"bench_metric": "ops_per_second", "test": "test_generate_level_and_query_state", '
              f'"value": {5 / elapsed:.2f}, "iterations": 5, '
              f'"duration_seconds": {elapsed:.6f}}}')


class TestLevelTraversalThroughput:
    """Measure speed of revisiting already-generated levels."""

    def test_revisit_5_levels_20_times(self, game):
        """Generate 5 levels, then cycle through them 20 times."""
        for depth in range(1, 6):
            game.set_level(depth)
        start = time.perf_counter()
        for i in range(20):
            game.set_level((i % 5) + 1)
        elapsed = time.perf_counter() - start
        print(f'{{"bench_metric": "ops_per_second", "test": "test_revisit_5_levels_20_times", '
              f'"value": {20 / elapsed:.2f}, "iterations": 20, '
              f'"duration_seconds": {elapsed:.6f}}}')
