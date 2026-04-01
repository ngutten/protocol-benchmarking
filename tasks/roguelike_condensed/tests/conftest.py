"""
Shared fixtures for Roguelike benchmark tests.

The roguelike task produces a C++ project with two build targets:
  - roguelike       (ncurses game binary, not used in automated tests)
  - test_harness    (headless engine with JSON-line protocol on stdin/stdout)

Tests communicate with test_harness via JSON.  Each request is a single JSON
object on one line; each response is likewise a single JSON object on one line.

Protocol overview
-----------------
Request:   {"cmd": "<command>", ...params}
Response:  {"ok": true, ...data}  or  {"ok": false, "error": "..."}

Commands (cumulative across stages):

  Stage 1 — Core Skeleton
    new_game        seed:int                     → ok
    execute         action:str                   → ok, accepted:bool, animations:[], round_ended:bool
    state                                        → ok, state:{player_pos, map, messages, screen_mode, seed}
    quit                                         → (clean exit)

  Stage 2 — Stats & Modifiers
    state  now includes: stats:{base:[], effective:[]}, derived:{max_hp, max_mp, ...},
                         level_info:{level, xp, xp_to_next, pending_points},
                         equipment_slots:{}
    set_xp          xp:int                       → ok

  Stage 3 — Turns, Enemies, AI
    spawn_creature  template:str, x:int, y:int   → ok, entity_id:int
    force_enemy_phase                            → ok, animations:[]
    move_to         x:int, y:int                 → ok  (teleport player, testing only)
    get_entity      entity:int                   → ok, entity:{pos, stats, ai, ...}
    state  now includes: player_bar:{current, max}, entities:{id→{pos, name, glyph}}

  Stage 4 — FOV & Lighting
    set_tile        x:int, y:int, tile_type:str  → ok  (test helper; "floor"/"wall"/etc.)
    state  now includes: visible_tiles:[[x,y],...], remembered_tiles:[[x,y],...],
                         creature_visibility:{id→state}

  Stage 5 — Combat & Status Effects
    set_hp          entity:int, hp:int           → ok  (entity=0 for player)
    apply_status    entity:int, status:str, duration_mp:int, magnitude:float → ok (test helper)
    state  now includes: hp, max_hp, mp, status_effects:[{type, duration_mp, magnitude}]

  Stage 6 — Items & Inventory
    create_item     template:str [, x:int, y:int]→ ok, item_id:int
    force_equip     item:int                     → ok  (test helper; equips by item ID)
    put_in_container item:int, container:int     → ok  (test helper; direct container move)
    take_from_container item:int, container:int  → ok  (test helper; direct container move)
    container_contents container:int             → ok, items:[{id, name, weight}]
    execute with inventory actions:
      "InvUp"/"InvDown"  move cursor
      "InvEquip"/"InvUnequip"/"InvUse"/"InvDrop"/"InvInspect"/"InvIdentify"
      "InvExpand"  expand/collapse container tree
      "InvPutIn"  begin put-in flow (auto-selects if one container)
      "InvTakeOut"  take contained item out
      "InvSelectContainer"  select container letter during put-in prompt
      "CloseInventory"  return to map
    state  now includes: inventory:[{id, name, weight, identified, contents:[...]}],
                         equipment:{slot→item_id}, ground_items:[{id, pos, name}]

  Stage 7 — Abilities
    learn_ability   ability:str                  → ok
    state  now includes: abilities:[{name, bound_key, mp_cost, slots}]

  Stage 8 — Ranged & Targeting
    (uses execute with action "Fire" + targeting commands "Tab", "Confirm", "Cancel")
    state  now includes: targeting:{active, cursor, valid_targets:[], hit_chance:float}

  Stage 9 — Procedural Generation
    set_level       level:int                    → ok
    state  now includes: dungeon_level, levels_visited,
                         map gains: stairs_up:{x,y}, stairs_down:{x,y}

  Stage 10 — Identification & Integration
    (no new commands; exercises cross-system interactions)

  Stage 11 — Save / Load
    save            [path:str]                   → ok, path:str
    load            path:str                     → ok

  Stage 12 — Multi-Tile Creatures
    spawn_creature  now accepts size:{w:int, h:int}
    get_entity      now includes body:{w, h, tiles:[[x,y],...]}
"""
import sys
import os
import json
import subprocess
import pytest


# ---------------------------------------------------------------------------
# Workspace discovery
# ---------------------------------------------------------------------------
ENGINE_CMD_ENV = "ENGINE_CMD"
_engine_cmd = os.environ.get(ENGINE_CMD_ENV, "")

if _engine_cmd and "cd " in _engine_cmd:
    _workspace = _engine_cmd.split("&&")[0].replace("cd ", "").strip()
else:
    _workspace = os.getcwd()


# ---------------------------------------------------------------------------
# Engine client
# ---------------------------------------------------------------------------

class RoguelikeEngine:
    """JSON-line protocol client for the roguelike test_harness binary."""

    def __init__(self, binary_path):
        self.binary_path = binary_path
        self.proc = subprocess.Popen(
            [binary_path],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )

    def _send(self, cmd_dict):
        """Send a command and return the parsed response."""
        line = json.dumps(cmd_dict, separators=(",", ":")) + "\n"
        try:
            self.proc.stdin.write(line)
            self.proc.stdin.flush()
        except BrokenPipeError:
            stderr = self.proc.stderr.read()
            raise RuntimeError(f"test_harness crashed (stdin closed): {stderr[:500]}")

        response_line = self.proc.stdout.readline()
        if not response_line:
            stderr = self.proc.stderr.read()
            raise RuntimeError(f"test_harness produced no output: {stderr[:500]}")

        resp = json.loads(response_line)
        if not resp.get("ok", False) and "error" in resp:
            # Return the error response rather than raising — tests may
            # intentionally provoke errors and assert on the message.
            pass
        return resp

    # -- Stage 1: Core Skeleton ------------------------------------------------

    def new_game(self, seed=42):
        """Start a new game with the given RNG seed."""
        return self._send({"cmd": "new_game", "seed": seed})

    def execute(self, action):
        """Execute a player command by name (e.g. 'MoveE', 'Wait', 'OpenStatPanel').

        Returns dict with keys: ok, accepted, animations (list), round_ended (bool).
        """
        return self._send({"cmd": "execute", "action": action})

    def state(self):
        """Snapshot the full game state.  Returns the 'state' sub-dict."""
        resp = self._send({"cmd": "state"})
        return resp.get("state", resp)

    # -- Stage 2: Stats & Modifiers --------------------------------------------

    def set_xp(self, xp):
        """Set the player's XP total (test helper)."""
        return self._send({"cmd": "set_xp", "xp": xp})

    # -- Stage 3: Turns, Enemies, AI ------------------------------------------

    def spawn_creature(self, template, x, y, **kwargs):
        """Spawn a creature on the current map.  Returns entity_id."""
        cmd = {"cmd": "spawn_creature", "template": template, "x": x, "y": y}
        cmd.update(kwargs)
        resp = self._send(cmd)
        return resp.get("entity_id")

    def force_enemy_phase(self):
        """Force enemy turn processing.  Returns animations list."""
        return self._send({"cmd": "force_enemy_phase"})

    def move_to(self, x, y):
        """Teleport the player to (x, y).  Test helper — not a game action."""
        return self._send({"cmd": "move_to", "x": x, "y": y})

    def get_entity(self, entity_id):
        """Get full state dict for an entity (0 = player)."""
        resp = self._send({"cmd": "get_entity", "entity": entity_id})
        return resp.get("entity", resp)

    def ai_state(self, entity_id):
        """Convenience: get just the AI sub-dict for an entity."""
        ent = self.get_entity(entity_id)
        return ent.get("ai", {})

    # -- Stage 4: FOV & Lighting -----------------------------------------------

    def set_tile(self, x, y, tile_type):
        """Set a tile type at position (x, y).  Test helper.

        tile_type: "floor", "wall", "stairs_up", "stairs_down"
        """
        return self._send({"cmd": "set_tile", "x": x, "y": y, "tile_type": tile_type})

    # -- Stage 5: Combat & Status Effects --------------------------------------

    def set_hp(self, entity_id, hp):
        """Set hit points for an entity (0 = player)."""
        return self._send({"cmd": "set_hp", "entity": entity_id, "hp": hp})

    def apply_status(self, entity_id, status, duration_mp=300, magnitude=1):
        """Apply a status effect to an entity.  Test helper."""
        return self._send({
            "cmd": "apply_status",
            "entity": entity_id,
            "status": status,
            "duration_mp": duration_mp,
            "magnitude": magnitude,
        })

    # -- Stage 6: Items & Inventory --------------------------------------------

    def create_item(self, template, x=None, y=None):
        """Create an item on the ground (if x,y given) or in player inventory."""
        cmd = {"cmd": "create_item", "template": template}
        if x is not None and y is not None:
            cmd["x"] = x
            cmd["y"] = y
        return self._send(cmd)

    def force_equip(self, item_id):
        """Equip an item by ID directly.  Test helper — bypasses inventory UI."""
        return self._send({"cmd": "force_equip", "item": item_id})

    def put_in_container(self, item_id, container_id):
        """Move an item into a container.  Corresponds to 'p' in inventory UI."""
        return self._send({
            "cmd": "put_in_container",
            "item": item_id,
            "container": container_id,
        })

    def take_from_container(self, item_id, container_id):
        """Remove an item from a container.  Corresponds to 't' in inventory UI."""
        return self._send({
            "cmd": "take_from_container",
            "item": item_id,
            "container": container_id,
        })

    def container_contents(self, container_id):
        """List items inside a container.  Returns list of {id, name, weight}."""
        resp = self._send({"cmd": "container_contents", "container": container_id})
        return resp.get("items", [])

    # -- Stage 7: Abilities ----------------------------------------------------

    def learn_ability(self, ability_name):
        """Teach the player an ability."""
        return self._send({"cmd": "learn_ability", "ability": ability_name})

    # -- Stage 9: Procedural Generation ----------------------------------------

    def set_level(self, level):
        """Jump to a dungeon depth (test helper)."""
        return self._send({"cmd": "set_level", "level": level})

    # -- Stage 11: Save / Load -------------------------------------------------

    def save_game(self, path=None):
        """Trigger a save.  Returns the path written."""
        cmd = {"cmd": "save"}
        if path:
            cmd["path"] = path
        return self._send(cmd)

    def load_game(self, path):
        """Load a save file."""
        return self._send({"cmd": "load", "path": path})

    # -- Lifecycle -------------------------------------------------------------

    def quit(self):
        """Ask the engine to shut down cleanly."""
        try:
            self._send({"cmd": "quit"})
        except (BrokenPipeError, RuntimeError):
            pass
        try:
            self.proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.proc.kill()

    def close(self):
        """Force-close the process."""
        if self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.proc.kill()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def build():
    """Build the C++ project once per test session.

    Looks for CMakeLists.txt (preferred) or Makefile in the workspace root.
    Must produce a ``test_harness`` binary.  Returns the absolute path to it.
    """
    cmake_path = os.path.join(_workspace, "CMakeLists.txt")
    makefile_path = os.path.join(_workspace, "Makefile")

    if os.path.exists(cmake_path):
        build_dir = os.path.join(_workspace, "build")
        os.makedirs(build_dir, exist_ok=True)
        subprocess.run(
            ["cmake", "..", "-DCMAKE_BUILD_TYPE=Release"],
            cwd=build_dir, check=True,
            capture_output=True, text=True, timeout=120,
        )
        subprocess.run(
            ["make", "-j4", "test_harness"],
            cwd=build_dir, check=True,
            capture_output=True, text=True, timeout=300,
        )
        binary = os.path.join(build_dir, "test_harness")
    elif os.path.exists(makefile_path):
        subprocess.run(
            ["make", "-j4", "test_harness"],
            cwd=_workspace, check=True,
            capture_output=True, text=True, timeout=300,
        )
        binary = os.path.join(_workspace, "test_harness")
    else:
        pytest.fail(
            f"No CMakeLists.txt or Makefile found in {_workspace}.  "
            "The project must provide a build system that produces a "
            "'test_harness' binary."
        )

    if not os.path.isfile(binary):
        pytest.fail(f"Build succeeded but test_harness binary not found at {binary}")

    return binary


@pytest.fixture
def engine(build):
    """A fresh test_harness process for each test function."""
    eng = RoguelikeEngine(build)
    yield eng
    eng.close()


@pytest.fixture
def game(engine):
    """An engine with a new game already started (seed 42)."""
    engine.new_game(seed=42)
    return engine
