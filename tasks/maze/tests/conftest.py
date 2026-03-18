"""
Shared fixtures for Maze Explorer benchmark tests.

Uses Playwright for browser-based testing of the web maze game.
An HTTP server serves the workspace files, and Playwright drives
a headless Chromium instance to test rendering, interaction, and the JS API.
"""
import os
import sys
import time
import json
import socket
import signal
import subprocess
import pytest


# ---------------------------------------------------------------------------
# Workspace discovery: the harness sets ENGINE_CMD to
#   "cd <workspace> && python3 -m http.server 8000"
# We parse the workspace path so we can serve those files.
# ---------------------------------------------------------------------------
ENGINE_CMD_ENV = "MAZE_ENGINE_CMD"
_engine_cmd = os.environ.get(ENGINE_CMD_ENV, os.environ.get("MINIDB_ENGINE_CMD", ""))

if _engine_cmd and "cd " in _engine_cmd:
    _workspace = _engine_cmd.split("&&")[0].replace("cd ", "").strip()
else:
    _workspace = os.getcwd()

# Also derive the task directory (where assets/ lives)
_task_dir = os.path.join(os.path.dirname(__file__), "..")


def _find_free_port():
    """Find a free TCP port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]


# ---------------------------------------------------------------------------
# HTTP server fixture (session-scoped)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def server_port():
    """Start an HTTP server serving the workspace directory. Return the port."""
    port = _find_free_port()
    proc = subprocess.Popen(
        [sys.executable, "-m", "http.server", str(port)],
        cwd=_workspace,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    # Wait for the server to be ready
    for _ in range(50):
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                break
        except OSError:
            time.sleep(0.1)
    yield port
    proc.send_signal(signal.SIGTERM)
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()


@pytest.fixture(scope="session")
def base_url(server_port):
    """Base URL for the game server."""
    return f"http://127.0.0.1:{server_port}"


# ---------------------------------------------------------------------------
# Playwright browser fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def browser():
    """Launch headless Chromium via Playwright."""
    from playwright.sync_api import sync_playwright
    pw = sync_playwright().start()
    br = pw.chromium.launch(headless=True)
    yield br
    br.close()
    pw.stop()


@pytest.fixture
def page(browser, base_url):
    """Fresh browser page navigated to the game's index.html."""
    pg = browser.new_page()
    pg.goto(f"{base_url}/index.html", wait_until="networkidle")
    # Wait for the game API to be available
    pg.wait_for_function("typeof window.game !== 'undefined'", timeout=10000)
    yield pg
    pg.close()


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def get_game_state(page):
    """Get current game state via the JS API."""
    return page.evaluate("""() => ({
        position: window.game.getPlayerPosition(),
        direction: window.game.getPlayerDirection(),
        goalReached: window.game.isGoalReached(),
        visitedCells: window.game.getVisitedCells(),
        mazeWidth: window.game.getMazeWidth(),
        mazeHeight: window.game.getMazeHeight(),
    })""")


def get_player_position(page):
    """Get player position as (x, y) tuple."""
    pos = page.evaluate("() => window.game.getPlayerPosition()")
    return (pos["x"], pos["y"])


def get_player_direction(page):
    """Get player direction as a string."""
    return page.evaluate("() => window.game.getPlayerDirection()")


def press_game_key(page, key, wait_ms=100):
    """Press a game key and wait briefly for the render to update."""
    page.keyboard.press(key)
    page.wait_for_timeout(wait_ms)


def get_canvas_pixel(page, selector, x, y):
    """Get the RGBA pixel value at (x, y) on a canvas element."""
    return page.evaluate("""([sel, px, py]) => {
        const el = document.querySelector(sel);
        if (!el) return null;
        // If it's a canvas, read directly
        if (el.tagName === 'CANVAS') {
            const ctx = el.getContext('2d');
            const data = ctx.getImageData(px, py, 1, 1).data;
            return [data[0], data[1], data[2], data[3]];
        }
        // If it contains a canvas, use that
        const canvas = el.querySelector('canvas');
        if (canvas) {
            const ctx = canvas.getContext('2d');
            const data = ctx.getImageData(px, py, 1, 1).data;
            return [data[0], data[1], data[2], data[3]];
        }
        return null;
    }""", [selector, x, y])


def get_element_screenshot_pixels(page, selector):
    """Take a screenshot of an element and return it as raw pixel data.

    Returns (width, height, pixels) where pixels is a flat list of RGBA values,
    or None if the element is not found.
    """
    screenshot_bytes = page.locator(selector).screenshot()
    if not screenshot_bytes:
        return None
    from PIL import Image
    import io
    img = Image.open(io.BytesIO(screenshot_bytes))
    img = img.convert("RGBA")
    return img.size[0], img.size[1], list(img.getdata())


def sample_region_colors(page, selector, x, y, w, h):
    """Sample a rectangular region of a canvas and return average RGB."""
    return page.evaluate("""([sel, rx, ry, rw, rh]) => {
        const el = document.querySelector(sel);
        if (!el) return null;
        const canvas = el.tagName === 'CANVAS' ? el : el.querySelector('canvas');
        if (!canvas) return null;
        const ctx = canvas.getContext('2d');
        const data = ctx.getImageData(rx, ry, rw, rh).data;
        let r = 0, g = 0, b = 0, count = 0;
        for (let i = 0; i < data.length; i += 4) {
            r += data[i]; g += data[i+1]; b += data[i+2]; count++;
        }
        return [Math.round(r/count), Math.round(g/count), Math.round(b/count)];
    }""", [selector, x, y, w, h])


def get_element_dimensions(page, selector):
    """Get element width and height."""
    return page.evaluate("""(sel) => {
        const el = document.querySelector(sel);
        if (!el) return null;
        const rect = el.getBoundingClientRect();
        return {width: rect.width, height: rect.height};
    }""", selector)


def get_maze_cell(page, x, y):
    """Get the maze cell character at (x, y)."""
    return page.evaluate("([x, y]) => window.game.getMazeCell(x, y)", [x, y])


def navigate_to_cell(page, target_x, target_y, max_steps=500):
    """Navigate the player to a target cell using BFS pathfinding.

    Reads the full maze grid via the JS API, computes a shortest path with
    BFS, then executes the turn/move sequence.  Returns True if the player
    reached the target.
    """
    from collections import deque

    traversable = {".", "@", "!", "%"}
    deltas = {"N": (0, -1), "E": (1, 0), "S": (0, 1), "W": (-1, 0)}
    dir_order = ["N", "E", "S", "W"]
    turn_right = {"N": "E", "E": "S", "S": "W", "W": "N"}

    pos = get_player_position(page)
    start = (pos[0], pos[1])
    goal = (target_x, target_y)
    if start == goal:
        return True

    # Read the maze grid once
    state = get_game_state(page)
    w, h = state["mazeWidth"], state["mazeHeight"]
    grid = {}
    for y in range(h):
        for x in range(w):
            grid[(x, y)] = get_maze_cell(page, x, y)

    # BFS to find shortest path
    queue = deque([start])
    came_from = {start: None}
    while queue:
        cx, cy = queue.popleft()
        if (cx, cy) == goal:
            break
        for d, (ddx, ddy) in deltas.items():
            nx, ny = cx + ddx, cy + ddy
            if (nx, ny) not in came_from and grid.get((nx, ny)) in traversable:
                came_from[(nx, ny)] = (cx, cy)
                queue.append((nx, ny))
    else:
        # goal not reachable
        return False

    if goal not in came_from:
        return False

    # Reconstruct path as list of (x, y) positions
    path = []
    node = goal
    while node is not None:
        path.append(node)
        node = came_from[node]
    path.reverse()

    # Execute moves along the path
    for i in range(1, len(path)):
        if i > max_steps:
            break
        prev = path[i - 1]
        nxt = path[i]
        dx, dy = nxt[0] - prev[0], nxt[1] - prev[1]
        needed = None
        for d, (ddx, ddy) in deltas.items():
            if (ddx, ddy) == (dx, dy):
                needed = d
                break

        # Turn to face the needed direction
        current_dir = get_player_direction(page)
        if current_dir != needed:
            # Compute minimal turns
            ci = dir_order.index(current_dir)
            ni = dir_order.index(needed)
            right_turns = (ni - ci) % 4
            if right_turns == 1:
                press_game_key(page, "d")
            elif right_turns == 2:
                press_game_key(page, "d")
                press_game_key(page, "d")
            elif right_turns == 3:
                press_game_key(page, "a")

        # Move forward
        press_game_key(page, "w")

    final = get_player_position(page)
    return final[0] == target_x and final[1] == target_y


def find_cell_of_type(page, cell_type):
    """Find the first cell of a given type in the maze. Returns (x, y) or None."""
    state = get_game_state(page)
    w, h = state["mazeWidth"], state["mazeHeight"]
    for y in range(h):
        for x in range(w):
            if get_maze_cell(page, x, y) == cell_type:
                return (x, y)
    return None


def find_adjacent_open_cell(page, target_x, target_y):
    """Find an open (traversable) cell adjacent to the given cell.
    Returns (x, y, direction_to_face_target) or None.
    """
    state = get_game_state(page)
    w, h = state["mazeWidth"], state["mazeHeight"]
    neighbors = [
        (target_x, target_y - 1, "S"),  # Cell above target, facing S to look at it
        (target_x + 1, target_y, "W"),  # Cell right of target, facing W
        (target_x, target_y + 1, "N"),  # Cell below target, facing N
        (target_x - 1, target_y, "E"),  # Cell left of target, facing E
    ]
    for nx, ny, facing in neighbors:
        if 0 <= nx < w and 0 <= ny < h:
            cell = get_maze_cell(page, nx, ny)
            if cell in (".", "@", "!"):
                return (nx, ny, facing)
    return None


def face_direction(page, target_dir):
    """Turn the player to face a specific direction."""
    turn_right = {"N": "E", "E": "S", "S": "W", "W": "N"}
    for _ in range(4):
        current = get_player_direction(page)
        if current == target_dir:
            return
        press_game_key(page, "d")
