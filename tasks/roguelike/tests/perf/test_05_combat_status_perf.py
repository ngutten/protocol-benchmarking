"""Performance benchmarks for Stage 5: Combat & Status Effects."""
import time


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
