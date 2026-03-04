"""Browser-based experiment UI with embedded terminal.

Serves a single-page dashboard with xterm.js connected via WebSocket
to a PTY running claude code. The harness auto-launches claude with the
right model/working dir/prompt for each stage.
"""
import asyncio
import fcntl
import json
import os
import pty
import signal
import struct
import termios
import time
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse

from .experiment import Experiment, setup_run_directory
from .metrics import collect_stage_metrics
from .protocols import ALL_PROTOCOLS
from .token_usage import get_session_token_usage


app = FastAPI()

# Global experiment state (single-user server)
state = {
    "experiment": None,
    "current_stage_idx": -1,
    "stages": [],
    "stage_metrics": [],
    "pty_fd": None,
    "child_pid": None,
    "stage_start_time": None,
    "presence_segments": [],
    "presence_status": "active",
    "presence_segment_start": None,
    "paused": False,
    "protocol": None,
}


def _find_latest_session_id(workspace_path: str) -> str:
    """Find the most recent session JSONL file matching the workspace path."""
    claude_dir = Path.home() / ".claude" / "projects"
    if not claude_dir.exists():
        return ""

    # Claude encodes project paths as directory names
    best_file = None
    best_mtime = 0

    for dirpath, _, filenames in os.walk(claude_dir):
        for fname in filenames:
            if fname.endswith(".jsonl"):
                fpath = Path(dirpath) / fname
                mtime = fpath.stat().st_mtime
                if mtime > best_mtime:
                    best_mtime = mtime
                    best_file = fpath

    if best_file and best_mtime > (time.time() - 3600):  # within last hour
        return best_file.stem  # filename without .jsonl is the session ID

    return ""


def init_experiment(task_dir: str, protocol_name: str, work_dir: str = None,
                    log_dir: str = None, engine_cmd: str = "python3 minidb.py",
                    model: str = None, run_id: str = None):
    """Initialize the experiment and populate global state."""
    protocol = ALL_PROTOCOLS[protocol_name]
    if model:
        protocol.model = model

    if not work_dir or not log_dir:
        rid = run_id or f"{protocol_name}_{int(time.time())}"
        dirs = setup_run_directory(rid, task_dir, protocol)
        work_dir = work_dir or dirs["workspace"]
        log_dir = log_dir or dirs["results"]

    exp = Experiment(
        task_dir=task_dir,
        protocol_name=protocol_name,
        work_dir=work_dir,
        log_dir=log_dir,
        engine_cmd=engine_cmd,
    )
    exp.setup()

    state["experiment"] = exp
    state["stages"] = list(exp.stages)
    state["current_stage_idx"] = -1
    state["stage_metrics"] = []
    state["protocol"] = protocol


def _spawn_claude_pty(work_dir: str, prompt: str, protocol) -> tuple:
    """Spawn claude in a PTY. Returns (master_fd, child_pid)."""
    cmd_parts = ["claude", "--model", protocol.model]

    if protocol.custom_command:
        from .claude_runner import _expand_custom_command
        cmd_parts = _expand_custom_command(protocol, prompt, work_dir)
    else:
        for tool in protocol.get_allowed_tools():
            cmd_parts.extend(["--allowedTools", tool])
        cmd_parts.append(prompt)

    env = os.environ.copy()
    env["TERM"] = "xterm-256color"

    child_pid, master_fd = pty.fork()
    if child_pid == 0:
        # Child process
        os.chdir(work_dir)
        os.execvpe(cmd_parts[0], cmd_parts, env)
    else:
        # Set non-blocking on master
        flag = fcntl.fcntl(master_fd, fcntl.F_GETFL)
        fcntl.fcntl(master_fd, fcntl.F_SETFL, flag | os.O_NONBLOCK)
        return master_fd, child_pid


def _kill_pty():
    """Kill the current PTY process if running."""
    if state["child_pid"]:
        try:
            os.kill(state["child_pid"], signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            os.waitpid(state["child_pid"], os.WNOHANG)
        except ChildProcessError:
            pass
        state["child_pid"] = None
    if state["pty_fd"] is not None:
        try:
            os.close(state["pty_fd"])
        except OSError:
            pass
        state["pty_fd"] = None


def _compute_human_time() -> float:
    """Compute total active human time from presence segments."""
    total = 0.0
    for seg in state["presence_segments"]:
        if seg["status"] == "active":
            end = seg.get("end", time.time())
            total += end - seg["start"]
    return total


# ---- API Routes ----

@app.get("/")
async def index():
    return HTMLResponse(DASHBOARD_HTML)


@app.get("/api/state")
async def get_state():
    exp = state["experiment"]
    stages_info = []
    for i, sid in enumerate(state["stages"]):
        info = {"id": sid, "status": "pending"}
        if i < len(state["stage_metrics"]):
            info["status"] = "completed"
            info["metrics"] = state["stage_metrics"][i]
        elif i == state["current_stage_idx"]:
            info["status"] = "in_progress"
        stages_info.append(info)

    return {
        "stages": stages_info,
        "current_stage_idx": state["current_stage_idx"],
        "protocol": state["protocol"].name if state["protocol"] else None,
        "model": state["protocol"].model if state["protocol"] else None,
        "paused": state["paused"],
        "presence_status": state["presence_status"],
        "pty_active": state["child_pid"] is not None,
    }


@app.post("/api/stage/start")
async def start_stage():
    exp = state["experiment"]
    if not exp:
        return {"error": "No experiment initialized"}

    next_idx = len(state["stage_metrics"])
    if next_idx >= len(state["stages"]):
        return {"error": "All stages completed"}

    stage_id = state["stages"][next_idx]
    state["current_stage_idx"] = next_idx

    exp.prepare_stage(stage_id)
    prompt = exp.build_stage_prompt(stage_id)

    # Start presence tracking
    state["presence_segments"] = []
    state["presence_status"] = "active"
    state["presence_segment_start"] = time.time()
    state["presence_segments"].append({
        "start": time.time(), "status": "active"
    })
    state["stage_start_time"] = time.time()

    # Spawn claude in PTY
    _kill_pty()
    master_fd, child_pid = _spawn_claude_pty(
        str(exp.work_dir), prompt, state["protocol"]
    )
    state["pty_fd"] = master_fd
    state["child_pid"] = child_pid

    return {"stage_id": stage_id, "stage_idx": next_idx, "prompt": prompt}


@app.post("/api/stage/complete")
async def complete_stage():
    exp = state["experiment"]
    if exp is None or state["current_stage_idx"] < 0:
        return {"error": "No stage in progress"}

    stage_id = state["stages"][state["current_stage_idx"]]

    # Close presence segment
    if state["presence_segments"]:
        state["presence_segments"][-1]["end"] = time.time()

    human_time = _compute_human_time()

    # Kill PTY
    _kill_pty()

    # Find session ID from recent JSONL files
    session_id = _find_latest_session_id(str(exp.work_dir))

    # Get token usage
    token_data = None
    if session_id:
        usage = get_session_token_usage(session_id)
        if usage["total_tokens"] > 0:
            token_data = usage

    # Complete stage via experiment
    metrics = exp.complete_stage(stage_id, human_time=human_time, token_data=token_data)
    metrics_dict = metrics.to_dict()

    state["stage_metrics"].append(metrics_dict)
    state["current_stage_idx"] = -1

    # Auto-save log
    exp.save_log()

    return {"stage_id": stage_id, "metrics": metrics_dict}


@app.post("/api/stage/skip")
async def skip_stage():
    exp = state["experiment"]
    if not exp:
        return {"error": "No experiment initialized"}

    next_idx = state["current_stage_idx"] if state["current_stage_idx"] >= 0 else len(state["stage_metrics"])
    if next_idx >= len(state["stages"]):
        return {"error": "All stages completed"}

    _kill_pty()
    stage_id = state["stages"][next_idx]
    state["stage_metrics"].append({"stage_id": stage_id, "skipped": True})
    state["current_stage_idx"] = -1
    exp.completed_stages.append(stage_id)
    return {"stage_id": stage_id, "skipped": True}


@app.post("/api/presence/toggle")
async def toggle_presence():
    now = time.time()
    if state["presence_segments"]:
        state["presence_segments"][-1]["end"] = now

    new_status = "away" if state["presence_status"] == "active" else "active"
    state["presence_status"] = new_status
    state["presence_segments"].append({"start": now, "status": new_status})
    return {"status": new_status}


@app.post("/api/experiment/abort")
async def abort_experiment():
    _kill_pty()
    exp = state["experiment"]
    if exp:
        exp.save_log()
    return {"aborted": True}


@app.websocket("/ws/terminal")
async def terminal_ws(ws: WebSocket):
    """WebSocket bridge between xterm.js and the PTY."""
    await ws.accept()

    if state["pty_fd"] is None:
        await ws.send_text("\r\nNo terminal session active. Click 'Start Stage' first.\r\n")
        await ws.close()
        return

    fd = state["pty_fd"]

    async def read_pty():
        """Read from PTY and send to WebSocket."""
        loop = asyncio.get_event_loop()
        while True:
            try:
                data = await loop.run_in_executor(None, _blocking_read_pty, fd)
                if data is None:
                    # Process exited (OSError/EOF)
                    await ws.send_text("\r\n[Process exited]\r\n")
                    break
                elif data:
                    await ws.send_bytes(data)
            except (OSError, WebSocketDisconnect):
                break

    async def write_pty():
        """Read from WebSocket and write to PTY."""
        while True:
            try:
                data = await ws.receive()
                if data.get("type") == "websocket.disconnect":
                    break
                payload = data.get("bytes") or (data.get("text", "").encode() if data.get("text") else None)
                if payload and state["pty_fd"] is not None:
                    os.write(state["pty_fd"], payload)
            except (WebSocketDisconnect, OSError):
                break

    try:
        await asyncio.gather(read_pty(), write_pty())
    except Exception:
        pass


@app.websocket("/ws/resize")
async def resize_ws(ws: WebSocket):
    """Receive terminal resize events."""
    await ws.accept()
    while True:
        try:
            data = await ws.receive_json()
            if state["pty_fd"] is not None:
                winsize = struct.pack("HHHH", data["rows"], data["cols"], 0, 0)
                fcntl.ioctl(state["pty_fd"], termios.TIOCSWINSZ, winsize)
        except (WebSocketDisconnect, OSError, KeyError):
            break


def _blocking_read_pty(fd, size=4096):
    """Blocking read from PTY fd. Returns bytes or empty on EOF/error."""
    import select
    try:
        r, _, _ = select.select([fd], [], [], 0.1)
        if r:
            return os.read(fd, size)
        return b""
    except OSError:
        return None


# ---- Dashboard HTML ----

DASHBOARD_HTML = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>Benchmark Experiment UI</title>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/@xterm/xterm@5/css/xterm.min.css">
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { font-family: system-ui, -apple-system, sans-serif; background: #1a1a2e; color: #e0e0e0; height: 100vh; display: flex; flex-direction: column; }
  header { background: #16213e; padding: 10px 20px; display: flex; align-items: center; justify-content: space-between; border-bottom: 1px solid #0f3460; }
  header h1 { font-size: 16px; color: #e94560; }
  .header-info { font-size: 13px; color: #888; }
  .main { display: flex; flex: 1; overflow: hidden; }
  .sidebar { width: 280px; background: #16213e; border-right: 1px solid #0f3460; overflow-y: auto; padding: 12px; flex-shrink: 0; }
  .terminal-area { flex: 1; display: flex; flex-direction: column; }
  .terminal-container { flex: 1; padding: 4px; }
  .controls { background: #16213e; border-top: 1px solid #0f3460; padding: 10px 16px; display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }
  .stage-item { padding: 8px 10px; margin-bottom: 4px; border-radius: 6px; font-size: 13px; cursor: default; }
  .stage-item.pending { background: #1a1a2e; color: #666; }
  .stage-item.in_progress { background: #0f3460; color: #e94560; font-weight: 600; }
  .stage-item.completed { background: #1a3a2e; color: #4ade80; }
  .stage-item.skipped { background: #1a1a2e; color: #555; text-decoration: line-through; }
  .metrics-mini { font-size: 11px; color: #888; margin-top: 4px; }
  button { padding: 6px 16px; border-radius: 6px; border: none; cursor: pointer; font-size: 13px; font-weight: 500; }
  .btn-primary { background: #e94560; color: #fff; }
  .btn-primary:hover { background: #c73e54; }
  .btn-primary:disabled { background: #555; cursor: not-allowed; }
  .btn-secondary { background: #0f3460; color: #e0e0e0; }
  .btn-secondary:hover { background: #1a4a80; }
  .btn-warning { background: #f59e0b; color: #000; }
  .btn-danger { background: #dc2626; color: #fff; }
  .presence-active { background: #22c55e; color: #000; }
  .presence-away { background: #f59e0b; color: #000; }
  .section-title { font-size: 11px; text-transform: uppercase; color: #666; margin: 12px 0 6px; letter-spacing: 0.5px; }
  #xterm { width: 100%; height: 100%; }
</style>
</head>
<body>
<header>
  <h1>Benchmark Experiment</h1>
  <span class="header-info" id="header-info">Loading...</span>
</header>
<div class="main">
  <div class="sidebar">
    <div class="section-title">Stages</div>
    <div id="stage-list"></div>
  </div>
  <div class="terminal-area">
    <div class="terminal-container" id="terminal-container">
      <div id="xterm"></div>
    </div>
    <div class="controls">
      <button class="btn-primary" id="btn-start" onclick="startStage()">Start Stage</button>
      <button class="btn-primary" id="btn-complete" onclick="completeStage()" disabled>Stage Complete</button>
      <button class="btn-secondary" id="btn-skip" onclick="skipStage()">Skip</button>
      <span style="flex:1"></span>
      <button class="presence-active" id="btn-presence" onclick="togglePresence()">Active</button>
      <button class="btn-danger" onclick="abortExperiment()">Abort</button>
    </div>
  </div>
</div>

<script src="https://cdn.jsdelivr.net/npm/@xterm/xterm@5/lib/xterm.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/@xterm/addon-fit@0.10/lib/addon-fit.min.js"></script>
<script>
  let term = null;
  let termWs = null;
  let resizeWs = null;
  let fitAddon = null;
  let dataDisposable = null;
  let resizeDisposable = null;

  function initTerminal() {
    term = new window.Terminal({
      cursorBlink: true,
      fontSize: 14,
      theme: { background: '#1a1a2e', foreground: '#e0e0e0', cursor: '#e94560' },
    });
    fitAddon = new window.FitAddon.FitAddon();
    term.loadAddon(fitAddon);
    term.open(document.getElementById('xterm'));
    fitAddon.fit();
    term.writeln('Welcome to the Benchmark Experiment UI.');
    term.writeln('Click "Start Stage" to begin.\\r\\n');

    window.addEventListener('resize', () => fitAddon.fit());
  }

  function connectTerminal() {
    if (termWs) { try { termWs.close(); } catch(e) {} }
    const proto = location.protocol === 'https:' ? 'wss' : 'ws';
    termWs = new WebSocket(`${proto}://${location.host}/ws/terminal`);
    termWs.binaryType = 'arraybuffer';
    termWs.onmessage = (e) => {
      if (e.data instanceof ArrayBuffer) {
        term.write(new Uint8Array(e.data));
      } else {
        term.write(e.data);
      }
    };
    termWs.onclose = () => {
      term.writeln('\\r\\n[Terminal disconnected]');
    };

    // Dispose previous handlers to avoid duplicate input on subsequent stages
    if (dataDisposable) { dataDisposable.dispose(); }
    dataDisposable = term.onData((data) => {
      if (termWs && termWs.readyState === WebSocket.OPEN) {
        termWs.send(data);
      }
    });

    // Resize WebSocket
    if (resizeWs) { try { resizeWs.close(); } catch(e) {} }
    resizeWs = new WebSocket(`${proto}://${location.host}/ws/resize`);
    const sendResize = () => {
      if (resizeWs && resizeWs.readyState === WebSocket.OPEN) {
        resizeWs.send(JSON.stringify({rows: term.rows, cols: term.cols}));
      }
    };
    resizeWs.onopen = sendResize;
    if (resizeDisposable) { resizeDisposable.dispose(); }
    resizeDisposable = term.onResize(sendResize);
    fitAddon.fit();
  }

  async function refreshState() {
    const res = await fetch('/api/state');
    const data = await res.json();
    document.getElementById('header-info').textContent =
      `Protocol: ${data.protocol || '?'} | Model: ${data.model || '?'}`;

    const list = document.getElementById('stage-list');
    list.innerHTML = '';
    data.stages.forEach((s) => {
      const div = document.createElement('div');
      div.className = 'stage-item ' + s.status;
      let label = s.id.replace(/_/g, ' ');
      div.innerHTML = `<div>${label}</div>`;
      if (s.metrics && !s.metrics.skipped) {
        div.innerHTML += `<div class="metrics-mini">
          Train: ${s.metrics.training_tests_passed}/${s.metrics.training_tests_total}
          | Holdout: ${s.metrics.holdout_tests_passed}/${s.metrics.holdout_tests_total}
          | Tokens: ${(s.metrics.total_tokens||0).toLocaleString()}
        </div>`;
      } else if (s.metrics && s.metrics.skipped) {
        div.className = 'stage-item skipped';
        div.innerHTML += `<div class="metrics-mini">Skipped</div>`;
      }
      list.appendChild(div);
    });

    const hasActive = data.current_stage_idx >= 0;
    const allDone = data.stages.every(s => s.status === 'completed' || s.metrics?.skipped);
    document.getElementById('btn-start').disabled = hasActive || allDone;
    document.getElementById('btn-complete').disabled = !hasActive;
    document.getElementById('btn-skip').disabled = allDone;

    const btn = document.getElementById('btn-presence');
    btn.textContent = data.presence_status === 'active' ? 'Active' : 'Away';
    btn.className = data.presence_status === 'active' ? 'presence-active' : 'presence-away';
  }

  async function startStage() {
    term.clear();
    const res = await fetch('/api/stage/start', {method: 'POST'});
    const data = await res.json();
    if (data.error) { term.writeln('Error: ' + data.error); return; }
    term.writeln(`Starting stage: ${data.stage_id}\\r\\n`);
    connectTerminal();
    refreshState();
  }

  async function completeStage() {
    document.getElementById('btn-complete').disabled = true;
    term.writeln('\\r\\nCollecting metrics...');
    const res = await fetch('/api/stage/complete', {method: 'POST'});
    const data = await res.json();
    if (data.error) { term.writeln('Error: ' + data.error); return; }
    const m = data.metrics;
    term.writeln(`\\r\\n--- Stage ${data.stage_id} Complete ---`);
    term.writeln(`Training: ${m.training_tests_passed}/${m.training_tests_total}`);
    term.writeln(`Holdout: ${m.holdout_tests_passed}/${m.holdout_tests_total}`);
    term.writeln(`Tokens: ${(m.total_tokens||0).toLocaleString()}`);
    term.writeln(`Code: ${m.code_lines} lines\\r\\n`);
    refreshState();
  }

  async function skipStage() {
    const res = await fetch('/api/stage/skip', {method: 'POST'});
    await res.json();
    refreshState();
  }

  async function togglePresence() {
    const res = await fetch('/api/presence/toggle', {method: 'POST'});
    await res.json();
    refreshState();
  }

  async function abortExperiment() {
    if (!confirm('Abort the experiment? Progress will be saved.')) return;
    await fetch('/api/experiment/abort', {method: 'POST'});
    term.writeln('\\r\\nExperiment aborted. Log saved.');
    refreshState();
  }

  // Init
  initTerminal();
  refreshState();
  setInterval(refreshState, 5000);
</script>
</body>
</html>
"""


def launch_ui(task_dir: str, protocol_name: str, host: str = "0.0.0.0",
              port: int = 8765, **kwargs):
    """Initialize experiment and start the web server."""
    import uvicorn
    init_experiment(task_dir, protocol_name, **kwargs)
    print(f"\n  Experiment UI: http://localhost:{port}\n")
    uvicorn.run(app, host=host, port=port, log_level="warning")
