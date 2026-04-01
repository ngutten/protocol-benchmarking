"""Performance benchmarks for Stage 12: Multi-Tile Creatures."""
import time


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
