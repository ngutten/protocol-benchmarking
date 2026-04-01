"""Performance benchmarks for Stage 7: Abilities."""
import time


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
