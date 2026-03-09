"""Browser-based experiment UI with embedded terminal.

Serves a single-page dashboard with xterm.js connected via WebSocket
to a PTY running claude code. The harness auto-launches claude with the
right model/working dir/prompt for each stage.
"""
import asyncio
import fcntl
import json
import math
import os
import pty
import shutil
import signal
import struct
import termios
import time
import yaml
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse

from .experiment import Experiment, setup_run_directory, load_task_config, resolve_pipeline
from .metrics import collect_stage_metrics
from .protocols import ALL_PROTOCOLS
from .state_tree import StateTree, TreeNode
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
    "auto_mode": False,
    "auto_advance": False,
    "auto_status": None,       # None, "running", "completing", "advancing"
    "pty_monitor_task": None,  # asyncio.Task for PTY exit monitoring
    "pty_generation": 0,       # incremented each time a new PTY is spawned
    # Deferred init fields
    "task_dir": None,
    "launch_kwargs": {},
    "default_protocol": None,
    "harness_log": [],  # circular buffer of harness debug messages
}

_HARNESS_LOG_MAX = 200


def _harness_log(msg: str):
    """Append a timestamped message to the harness debug log."""
    ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    entry = f"[{ts}] {msg}"
    state["harness_log"].append(entry)
    if len(state["harness_log"]) > _HARNESS_LOG_MAX:
        state["harness_log"] = state["harness_log"][-_HARNESS_LOG_MAX:]


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


def _spawn_claude_pty(work_dir: str, prompt: str, protocol, headless: bool = False) -> tuple:
    """Spawn claude in a PTY. Returns (master_fd, child_pid).

    If headless=True, uses `claude -p` so the process exits on completion.
    The PTY still provides terminal I/O for permission prompts.
    """
    cmd_parts = ["claude", "--model", protocol.model]

    if protocol.custom_command:
        from .claude_runner import _expand_custom_command
        cmd_parts = _expand_custom_command(protocol, prompt, work_dir)
    else:
        if headless:
            cmd_parts.extend(["-p", "--output-format", "text"])
        if getattr(protocol, 'permission_mode', None):
            cmd_parts.extend(["--permission-mode", protocol.permission_mode])
        elif headless:
            cmd_parts.extend(["--permission-mode", "acceptEdits"])
        for tool in protocol.get_allowed_tools():
            cmd_parts.extend(["--allowedTools", tool])
        # Use -- to separate flags from the prompt argument
        cmd_parts.append("--")
        cmd_parts.append(prompt)

    env = os.environ.copy()
    env["TERM"] = "xterm-256color"

    _harness_log(f"spawn: headless={headless} cmd={cmd_parts[0]}...{cmd_parts[1:3]} (prompt {len(prompt)} chars)")

    child_pid, master_fd = pty.fork()
    if child_pid == 0:
        os.chdir(work_dir)
        os.execvpe(cmd_parts[0], cmd_parts, env)
    else:
        flag = fcntl.fcntl(master_fd, fcntl.F_GETFL)
        fcntl.fcntl(master_fd, fcntl.F_SETFL, flag | os.O_NONBLOCK)
        return master_fd, child_pid


def _kill_pty():
    """Kill the current PTY process if running."""
    # Cancel any PTY monitor task
    if state["pty_monitor_task"] is not None:
        state["pty_monitor_task"].cancel()
        state["pty_monitor_task"] = None
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


def _consolidate_log(exp):
    """Copy the experiment log JSON and merge tree nodes into the consolidated logs/ directory."""
    if not exp or not exp.log_dir:
        return
    consolidated_dir = Path("logs")
    consolidated_dir.mkdir(exist_ok=True)

    # Copy metrics JSON
    log_file = Path(exp.log_dir) / f"{exp.run_id}.json"
    if log_file.exists():
        shutil.copy2(str(log_file), str(consolidated_dir / log_file.name))

    # Merge run's tree nodes into the consolidated tree
    run_tree_file = Path(exp.log_dir) / "experiment_tree.json"
    if run_tree_file.exists():
        consolidated_tree = StateTree(str(consolidated_dir))
        with open(run_tree_file) as f:
            run_data = json.load(f)
        for nid, ndata in run_data.get("nodes", {}).items():
            if nid not in consolidated_tree.nodes:
                consolidated_tree.nodes[nid] = TreeNode.from_dict(ndata)
        # Update next ID counter
        if consolidated_tree.nodes:
            max_num = max(
                int(nid.split("_")[1]) for nid in consolidated_tree.nodes
                if nid.startswith("node_") and nid.split("_")[1].isdigit()
            )
            consolidated_tree._next_id = max(consolidated_tree._next_id, max_num + 1)
        consolidated_tree.save()


async def _monitor_pty_exit():
    """Background task that monitors the child PID for exit.

    When the process exits (claude -p finishes), auto-completes the stage
    and optionally auto-advances to the next stage.
    """
    child_pid = state["child_pid"]
    if not child_pid:
        _harness_log("monitor: no child_pid, exiting")
        return

    _harness_log(f"monitor: watching PID {child_pid}")
    loop = asyncio.get_event_loop()

    def _wait_for_exit():
        """Block until child process exits."""
        while True:
            try:
                pid, exit_status = os.waitpid(child_pid, os.WNOHANG)
                if pid != 0:
                    _harness_log(f"monitor: PID {child_pid} exited (status={exit_status})")
                    return exit_status
            except ChildProcessError:
                _harness_log(f"monitor: PID {child_pid} already reaped")
                return 0
            time.sleep(0.25)

    try:
        await loop.run_in_executor(None, _wait_for_exit)
    except asyncio.CancelledError:
        _harness_log("monitor: cancelled")
        return

    # Brief delay for final PTY output to flush
    await asyncio.sleep(0.5)

    # Auto-complete the stage (check it hasn't been manually completed already)
    if state["current_stage_idx"] < 0:
        _harness_log("monitor: stage already completed (manual or race), skipping auto-complete")
        return

    await _auto_complete_stage()

    # Auto-advance if enabled
    if state["auto_advance"]:
        await _auto_start_next_stage()


async def _auto_complete_stage():
    """Programmatically complete the current stage (same logic as POST /api/stage/complete)."""
    exp = state["experiment"]
    if exp is None or state["current_stage_idx"] < 0:
        _harness_log(f"auto_complete: skipped (exp={exp is not None}, idx={state['current_stage_idx']})")
        return

    stage_id = state["stages"][state["current_stage_idx"]]
    _harness_log(f"auto_complete: starting for stage {stage_id} (idx={state['current_stage_idx']})")
    state["auto_status"] = "completing"

    # Close presence segment
    if state["presence_segments"]:
        state["presence_segments"][-1]["end"] = time.time()

    human_time = _compute_human_time()
    wall_time = time.time() - state["stage_start_time"] if state["stage_start_time"] else human_time

    # Don't kill PTY here — process already exited, just clean up fd
    # Clear the child_pid since the process already exited (waitpid was done in monitor)
    state["child_pid"] = None
    state["pty_monitor_task"] = None
    if state["pty_fd"] is not None:
        try:
            os.close(state["pty_fd"])
        except OSError:
            pass
        state["pty_fd"] = None

    # Find session ID from recent JSONL files
    session_id = _find_latest_session_id(str(exp.work_dir))

    # Get token usage
    token_data = None
    if session_id:
        usage = get_session_token_usage(session_id)
        if usage["total_tokens"] > 0:
            token_data = usage

    # Complete stage via experiment
    _harness_log(f"auto_complete: running metrics for {stage_id} (session={session_id}, tokens={token_data.get('total_tokens', 0) if token_data else 0})")
    try:
        metrics = exp.complete_stage(stage_id, human_time=human_time, wall_time=wall_time, token_data=token_data)
        metrics_dict = metrics.to_dict()
    except Exception as e:
        _harness_log(f"auto_complete: ERROR in complete_stage: {e}")
        state["auto_status"] = None
        state["current_stage_idx"] = -1
        return

    state["stage_metrics"].append(metrics_dict)
    state["current_stage_idx"] = -1
    state["auto_status"] = None
    _harness_log(f"auto_complete: done for {stage_id} (train={metrics_dict.get('training_tests_passed')}/{metrics_dict.get('training_tests_total')})")

    # Auto-save log and consolidate
    exp.save_log()
    _consolidate_log(exp)


async def _auto_start_next_stage():
    """Programmatically start the next stage after a brief delay."""
    exp = state["experiment"]
    if not exp:
        _harness_log("auto_advance: no experiment")
        return

    next_idx = len(state["stage_metrics"])
    if next_idx >= len(state["stages"]):
        _harness_log("auto_advance: all stages complete")
        state["auto_status"] = None
        return

    _harness_log(f"auto_advance: waiting 2s before stage {next_idx}")
    state["auto_status"] = "advancing"
    await asyncio.sleep(2)

    # Re-check in case user aborted during the delay
    if not state["auto_mode"] or state["experiment"] is None:
        _harness_log("auto_advance: aborted during delay")
        state["auto_status"] = None
        return

    next_idx = len(state["stage_metrics"])
    if next_idx >= len(state["stages"]):
        _harness_log("auto_advance: all stages complete (after delay)")
        state["auto_status"] = None
        return

    stage_id = state["stages"][next_idx]
    _harness_log(f"auto_advance: starting stage {stage_id} (idx={next_idx})")
    state["current_stage_idx"] = next_idx

    exp.prepare_stage(stage_id)
    prompt = exp.build_stage_prompt(stage_id)

    # Start presence tracking (away in semi-auto mode)
    state["presence_segments"] = []
    state["presence_status"] = "away"
    state["presence_segment_start"] = time.time()
    state["presence_segments"].append({
        "start": time.time(), "status": "away"
    })
    state["stage_start_time"] = time.time()

    # Spawn claude in PTY with headless mode
    _kill_pty()
    master_fd, child_pid = _spawn_claude_pty(
        str(exp.work_dir), prompt, state["protocol"], headless=True
    )
    state["pty_fd"] = master_fd
    state["child_pid"] = child_pid
    state["pty_generation"] += 1
    state["auto_status"] = "running"

    # Start monitoring for this new stage
    state["pty_monitor_task"] = asyncio.create_task(_monitor_pty_exit())


# ---- API Routes ----

@app.get("/")
async def index():
    return HTMLResponse(DASHBOARD_HTML)


@app.get("/api/protocols")
async def get_protocols():
    """Return all available protocols with metadata."""
    protocols = []
    for name, proto in sorted(ALL_PROTOCOLS.items()):
        protocols.append({
            "name": proto.name,
            "description": proto.description,
            "human_instructions": proto.human_instructions,
            "added_instructions": proto.added_instructions,
            "planning_phase": proto.planning_phase,
            "planning_prompt": proto.planning_prompt,
            "human_supervised": proto.human_supervised,
            "model": proto.model,
            "provides_training_tests": proto.provides_training_tests,
            "llm_writes_tests": proto.llm_writes_tests,
        })
    return {
        "protocols": protocols,
        "default": state["default_protocol"],
    }


from fastapi import Request as FastAPIRequest


@app.post("/api/experiment/init")
async def init_experiment_api(request: FastAPIRequest):
    """Initialize (or re-initialize) experiment with a chosen protocol."""
    body = await request.json()
    protocol_name = body.get("protocol")
    if not protocol_name or protocol_name not in ALL_PROTOCOLS:
        return {"error": f"Invalid protocol: {protocol_name}"}

    task_dir = state["task_dir"]
    if not task_dir:
        return {"error": "No task directory configured"}

    # Kill any running PTY
    _kill_pty()

    # Reset stage state
    state["presence_segments"] = []
    state["presence_status"] = "active"
    state["stage_metrics"] = []
    state["current_stage_idx"] = -1

    # Initialize with stored kwargs
    kwargs = dict(state["launch_kwargs"])
    kwargs["model"] = kwargs.pop("model", None)
    init_experiment(task_dir, protocol_name, **kwargs)

    exp = state["experiment"]
    return {
        "run_id": exp.run_id,
        "stages": list(exp.stages),
        "protocol": protocol_name,
    }


@app.post("/api/auto/configure")
async def configure_auto(request: FastAPIRequest):
    """Enable or disable semi-auto mode."""
    body = await request.json()
    state["auto_mode"] = bool(body.get("auto_mode", False))
    state["auto_advance"] = bool(body.get("auto_advance", state["auto_mode"]))
    return {
        "auto_mode": state["auto_mode"],
        "auto_advance": state["auto_advance"],
    }


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

    # Compute live stats
    live_stats = None
    if state["current_stage_idx"] >= 0 and state["stage_start_time"]:
        wall_elapsed = time.time() - state["stage_start_time"]
        human_time = _compute_human_time()
        # Try to get live token count
        live_tokens = 0
        if exp:
            session_id = _find_latest_session_id(str(exp.work_dir))
            if session_id:
                try:
                    usage = get_session_token_usage(session_id)
                    live_tokens = usage.get("total_tokens", 0)
                except Exception:
                    pass
        live_stats = {
            "wall_elapsed_seconds": round(wall_elapsed, 1),
            "human_time_seconds": round(human_time, 1),
            "live_tokens": live_tokens,
        }

    # Cumulative totals from completed stages
    cumulative_tokens = sum(
        m.get("total_tokens", 0) for m in state["stage_metrics"]
        if isinstance(m, dict) and not m.get("skipped")
    )
    cumulative_human_time = sum(
        m.get("human_time_seconds", 0) for m in state["stage_metrics"]
        if isinstance(m, dict) and not m.get("skipped")
    )

    return {
        "initialized": exp is not None,
        "stages": stages_info,
        "current_stage_idx": state["current_stage_idx"],
        "protocol": state["protocol"].name if state["protocol"] else None,
        "model": state["protocol"].model if state["protocol"] else None,
        "paused": state["paused"],
        "presence_status": state["presence_status"],
        "pty_active": state["child_pid"] is not None,
        "live_stats": live_stats,
        "cumulative_tokens": cumulative_tokens,
        "cumulative_human_time": round(cumulative_human_time, 1),
        "auto_mode": state["auto_mode"],
        "auto_advance": state["auto_advance"],
        "auto_status": state["auto_status"],
        "harness_log": state["harness_log"][-20:],  # last 20 entries for polling
    }


@app.get("/api/harness-log")
async def get_harness_log():
    """Return the full harness debug log."""
    return {"log": state["harness_log"]}


@app.post("/api/stage/start")
async def start_stage():
    exp = state["experiment"]
    if not exp:
        return {"error": "No experiment initialized"}

    next_idx = len(state["stage_metrics"])
    if next_idx >= len(state["stages"]):
        return {"error": "All stages completed"}

    stage_id = state["stages"][next_idx]
    _harness_log(f"start_stage: {stage_id} (idx={next_idx}, auto={state['auto_mode']})")
    state["current_stage_idx"] = next_idx

    exp.prepare_stage(stage_id)
    prompt = exp.build_stage_prompt(stage_id)

    # Start presence tracking (away by default in semi-auto mode)
    initial_presence = "away" if state["auto_mode"] else "active"
    state["presence_segments"] = []
    state["presence_status"] = initial_presence
    state["presence_segment_start"] = time.time()
    state["presence_segments"].append({
        "start": time.time(), "status": initial_presence
    })
    state["stage_start_time"] = time.time()

    # Spawn claude in PTY
    _kill_pty()
    headless = state["auto_mode"]
    master_fd, child_pid = _spawn_claude_pty(
        str(exp.work_dir), prompt, state["protocol"], headless=headless
    )
    state["pty_fd"] = master_fd
    state["child_pid"] = child_pid
    state["pty_generation"] += 1

    # In auto mode, start monitoring for process exit
    if headless:
        state["auto_status"] = "running"
        state["pty_monitor_task"] = asyncio.create_task(_monitor_pty_exit())

    return {"stage_id": stage_id, "stage_idx": next_idx, "prompt": prompt}


@app.post("/api/stage/complete")
async def complete_stage():
    exp = state["experiment"]
    if exp is None or state["current_stage_idx"] < 0:
        _harness_log(f"complete_stage: rejected (exp={exp is not None}, idx={state['current_stage_idx']}, auto_status={state['auto_status']})")
        return {"error": "No stage in progress"}

    stage_id = state["stages"][state["current_stage_idx"]]
    _harness_log(f"complete_stage: manual complete for {stage_id}")

    # Close presence segment
    if state["presence_segments"]:
        state["presence_segments"][-1]["end"] = time.time()

    human_time = _compute_human_time()
    wall_time = time.time() - state["stage_start_time"] if state["stage_start_time"] else human_time

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
    metrics = exp.complete_stage(stage_id, human_time=human_time, wall_time=wall_time, token_data=token_data)
    metrics_dict = metrics.to_dict()

    state["stage_metrics"].append(metrics_dict)
    state["current_stage_idx"] = -1

    # Auto-save log and consolidate
    exp.save_log()
    _consolidate_log(exp)

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
        _consolidate_log(exp)
    return {"aborted": True}


@app.get("/api/tree")
async def get_tree():
    """Return the experiment state tree."""
    log_dir = Path("logs")
    if not log_dir.exists():
        return {"nodes": {}}
    tree = StateTree(str(log_dir))
    return tree.to_dict()


@app.get("/api/pipelines")
async def get_pipelines():
    """Return available pipelines for the current task."""
    task_dir = state.get("task_dir")
    if not task_dir:
        return {"pipelines": {}}
    cfg = load_task_config(task_dir)
    return {"pipelines": cfg.get("pipelines", {})}


@app.get("/api/comparisons/available")
async def get_available_comparisons():
    """Return computable and missing differential comparisons."""
    log_dir = Path("logs")
    if not log_dir.exists():
        return {"available": [], "missing": []}
    tree = StateTree(str(log_dir))
    available = tree.list_available_comparisons()

    # Determine what's missing based on task pipelines
    task_dir = state.get("task_dir")
    missing = []
    if task_dir:
        cfg = load_task_config(task_dir)
        all_stages = [s["id"] for s in cfg.get("stages", [])]
        all_protocols = sorted(ALL_PROTOCOLS.keys())
        missing = tree.list_missing_comparisons(all_stages, all_protocols)

    return {"available": available, "missing": missing}


@app.post("/api/experiment/fork")
async def fork_experiment(request: FastAPIRequest):
    """Initialize a new experiment forked from an existing tree node."""
    body = await request.json()
    node_id = body.get("node_id")
    protocol_name = body.get("protocol")
    pipeline_name = body.get("pipeline")
    slots = body.get("slots", {})

    if not node_id:
        return {"error": "node_id is required"}
    if not protocol_name or protocol_name not in ALL_PROTOCOLS:
        return {"error": f"Invalid protocol: {protocol_name}"}

    task_dir = state["task_dir"]
    if not task_dir:
        return {"error": "No task directory configured"}

    _kill_pty()

    protocol = ALL_PROTOCOLS[protocol_name]
    kwargs = dict(state["launch_kwargs"])
    model = kwargs.pop("model", None)
    if model:
        protocol.model = model

    rid = f"fork_{protocol_name}_{int(time.time())}"
    dirs = setup_run_directory(rid, task_dir, protocol)

    exp = Experiment(
        task_dir=task_dir,
        protocol_name=protocol_name,
        work_dir=dirs["workspace"],
        log_dir=dirs["results"],
        engine_cmd=kwargs.get("engine_cmd", "python3 minidb.py"),
        pipeline_name=pipeline_name,
        slots=slots,
    )
    exp.setup(fork_from_node=node_id)

    state["experiment"] = exp
    state["stages"] = exp.get_pipeline_stages_list() if pipeline_name else list(exp.stages)
    state["current_stage_idx"] = -1
    state["stage_metrics"] = []
    state["protocol"] = protocol
    state["presence_segments"] = []
    state["presence_status"] = "active"

    # Mark forked stages as completed in metrics list
    for sid in exp.completed_stages:
        state["stage_metrics"].append({"stage_id": sid, "skipped": True, "forked": True})

    return {
        "run_id": exp.run_id,
        "stages": state["stages"],
        "protocol": protocol_name,
        "forked_from": node_id,
        "completed_stages": list(exp.completed_stages),
    }


@app.websocket("/ws/terminal")
async def terminal_ws(ws: WebSocket):
    """WebSocket bridge between xterm.js and the PTY.

    Reads from state["pty_fd"] dynamically so it survives stage transitions.
    When a PTY closes (process exit), waits briefly for a new PTY to appear
    (e.g. from auto-advance) instead of immediately disconnecting.
    """
    await ws.accept()

    if state["pty_fd"] is None:
        await ws.send_text("\r\nNo terminal session active. Click 'Start Stage' first.\r\n")
        await ws.close()
        return

    async def _notify_stage_transition(new_gen):
        """Send a stage transition banner to the terminal."""
        try:
            stage_idx = state["current_stage_idx"]
            if stage_idx >= 0 and stage_idx < len(state["stages"]):
                stage_id = state["stages"][stage_idx]
                await ws.send_text(f"\r\n\x1b[1;36m--- Starting stage: {stage_id} ---\x1b[0m\r\n\r\n")
        except (WebSocketDisconnect, OSError):
            pass

    async def read_pty():
        """Read from PTY and send to WebSocket, following fd changes across stages."""
        loop = asyncio.get_event_loop()
        current_fd = state["pty_fd"]
        current_gen = state["pty_generation"]
        try:
            while True:
                # Check if a new PTY generation appeared
                if state["pty_generation"] > current_gen and state["pty_fd"] is not None:
                    current_fd = state["pty_fd"]
                    current_gen = state["pty_generation"]
                    await _notify_stage_transition(current_gen)

                if current_fd is None or state["pty_fd"] is None:
                    # PTY closed — wait for a new one (auto-advance) or give up
                    new_fd, new_gen = await _wait_for_new_pty(current_gen)
                    if new_fd is None:
                        await ws.send_text("\r\n[Process exited]\r\n")
                        break
                    current_fd = new_fd
                    current_gen = new_gen
                    await _notify_stage_transition(current_gen)
                    continue

                try:
                    data = await loop.run_in_executor(None, _blocking_read_pty, current_fd)
                    if data is None:
                        # EOF — fd is dead. Wait for a replacement.
                        new_fd, new_gen = await _wait_for_new_pty(current_gen)
                        if new_fd is None:
                            await ws.send_text("\r\n[Process exited]\r\n")
                            break
                        current_fd = new_fd
                        current_gen = new_gen
                        await _notify_stage_transition(current_gen)
                    elif data:
                        await ws.send_bytes(data)
                except (OSError, WebSocketDisconnect):
                    break
        finally:
            # Close the WS so write_pty's ws.receive() also terminates,
            # allowing asyncio.gather to complete and the handler to exit.
            # This lets the frontend auto-reconnect detect the dead WS.
            try:
                await ws.close()
            except Exception:
                pass

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


async def _wait_for_new_pty(old_gen: int, timeout: float = 60.0):
    """Wait up to `timeout` seconds for a new PTY generation to appear.

    Returns (new_fd, new_gen) or (None, old_gen) if no new PTY appeared.
    Timeout is generous because metrics collection between stages can be slow.
    """
    if not state["auto_mode"]:
        return None, old_gen
    _harness_log(f"ws: waiting for new PTY (gen={old_gen}, timeout={timeout}s)")
    deadline = time.time() + timeout
    while time.time() < deadline:
        await asyncio.sleep(0.3)
        if state["pty_generation"] > old_gen and state["pty_fd"] is not None:
            _harness_log(f"ws: PTY gen {old_gen} -> {state['pty_generation']} (fd={state['pty_fd']})")
            return state["pty_fd"], state["pty_generation"]
    _harness_log(f"ws: no new PTY after {timeout}s (gen={old_gen})")
    return None, old_gen


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


# ---- Visualization API endpoints ----

def _effective_tokens(stage):
    """Cost-weighted tokens: cache reads at 0.1x, everything else at 1x."""
    return (stage.get("input_tokens", 0)
            + stage.get("output_tokens", 0)
            + stage.get("cache_creation_tokens", 0)
            + int(stage.get("cache_read_tokens", 0) * 0.1))


def _load_all_logs():
    """Load all experiment logs from logs/ directory (and subdirectories)."""
    logs = []
    logs_dir = Path("logs")
    if not logs_dir.exists():
        return logs
    for f in sorted(logs_dir.rglob("*.json")):
        if f.name == "experiment_tree.json":
            continue
        try:
            with open(f) as fh:
                log = json.load(fh)
            # Strip bulky test_results arrays, add effective_tokens
            for s in log.get("stages", []):
                s.pop("test_results", None)
                if "effective_tokens" not in s:
                    s["effective_tokens"] = _effective_tokens(s)
            logs.append(log)
        except (json.JSONDecodeError, KeyError):
            continue
    return logs


def _load_all_tasks():
    """Load all task configs from tasks/*/task.yaml."""
    tasks = {}
    for task_yaml in sorted(Path("tasks").glob("*/task.yaml")):
        try:
            with open(task_yaml) as f:
                cfg = yaml.safe_load(f)
            task_path = str(task_yaml.parent)
            stages = []
            for s in cfg.get("stages", []):
                if isinstance(s, dict) and "id" in s:
                    stages.append({
                        "id": s["id"],
                        "pipeline_tags": s.get("pipeline_tags", []),
                    })
            tasks[task_path] = {
                "name": cfg.get("name", task_yaml.parent.name),
                "stages": stages,
                "pipelines": cfg.get("pipelines", {}),
                "domain_tags": cfg.get("domain_tags", []),
            }
        except Exception:
            continue
    return tasks


@app.get("/api/logs")
async def get_logs():
    """Return all experiment logs with metrics (stripped of test_results)."""
    return {"runs": _load_all_logs()}


@app.get("/api/tasks")
async def get_tasks():
    """Return all task configurations with stage metadata."""
    return {"tasks": _load_all_tasks()}


@app.post("/api/differential/analyze")
async def analyze_differential(request: FastAPIRequest):
    """Compute A/B differential analysis.

    Body: {
        task: "tasks/minidb",
        group_a: [0, 1],         # stage indices for group A
        group_b: [2],            # stage indices for group B
        treatment: "plan_and_implement",
        baseline: "direct_tests_provided",
        metrics: ["holdout_accuracy", "effective_tokens"]
    }

    The treatment condition: treatment protocol on all A stages, baseline on all B stages.
    The baseline condition: baseline protocol on all A and B stages.
    """
    body = await request.json()
    task_path = body.get("task", "")
    group_a = body.get("group_a", [])
    group_b = body.get("group_b", [])
    treatment_proto = body.get("treatment", "")
    baseline_proto = body.get("baseline", "")
    metric_names = body.get("metrics", ["holdout_accuracy"])

    # Load task config to get stage IDs
    tasks = _load_all_tasks()
    task_cfg = tasks.get(task_path)
    if not task_cfg:
        return {"error": f"Task not found: {task_path}"}

    all_stage_ids = [s["id"] for s in task_cfg["stages"]]

    # Map group indices to stage IDs
    a_stages = set()
    b_stages = set()
    for idx in group_a:
        if 0 <= idx < len(all_stage_ids):
            a_stages.add(all_stage_ids[idx])
    for idx in group_b:
        if 0 <= idx < len(all_stage_ids):
            b_stages.add(all_stage_ids[idx])

    if not a_stages or not b_stages:
        return {"error": "Both groups A and B must have at least one stage"}

    # Load logs and filter to this task
    logs = _load_all_logs()
    task_logs = [l for l in logs if l.get("task", "").rstrip("/").endswith(task_path.split("/")[-1])]

    # For each log, determine per-stage protocol mapping
    def get_stage_protocol(log, stage_id):
        sp = log.get("stage_protocols", {})
        if stage_id in sp:
            return sp[stage_id]
        # Check stage-level protocol field
        for s in log.get("stages", []):
            if s["stage_id"] == stage_id or s["stage_id"].endswith(f"_{stage_id}"):
                return s.get("protocol", log.get("protocol"))
        return log.get("protocol")

    def match_stage_id(stage_id, log_stages):
        """Find a stage in log that matches (exact or with numeric prefix)."""
        for s in log_stages:
            sid = s["stage_id"]
            if sid == stage_id or sid.endswith(f"_{stage_id}"):
                return s
        return None

    # Find matching runs.
    # Treatment condition: treatment on A stages, baseline on B stages.
    # Baseline condition: baseline on all A+B stages.
    # For single-protocol runs, we also accept: treatment on all stages
    # (measures B-stage metrics after treatment was applied to A).
    treatment_metric_values = {m: [] for m in metric_names}
    baseline_metric_values = {m: [] for m in metric_names}
    found_treatment = False
    found_baseline = False

    for log in task_logs:
        stages_data = log.get("stages", [])
        proto_map = {}
        for sid in list(a_stages) + list(b_stages):
            proto_map[sid] = get_stage_protocol(log, sid)

        # Ideal match: treatment on A, baseline on B (mixed-protocol run)
        a_treatment = all(proto_map.get(s) == treatment_proto for s in a_stages)
        b_baseline = all(proto_map.get(s) == baseline_proto for s in b_stages)

        # Also accept: treatment on all stages (single-protocol run with treatment)
        all_treatment = all(proto_map.get(s) == treatment_proto for s in a_stages | b_stages)

        # Baseline: baseline on all stages
        all_baseline = all(proto_map.get(s) == baseline_proto for s in a_stages | b_stages)

        if (a_treatment and b_baseline) or all_treatment:
            found_treatment = True
            for sid in b_stages:
                stage_data = match_stage_id(sid, stages_data)
                if stage_data:
                    for m in metric_names:
                        val = stage_data.get(m)
                        if val is not None:
                            treatment_metric_values[m].append(val)

        if all_baseline:
            found_baseline = True
            for sid in b_stages:
                stage_data = match_stage_id(sid, stages_data)
                if stage_data:
                    for m in metric_names:
                        val = stage_data.get(m)
                        if val is not None:
                            baseline_metric_values[m].append(val)

    # Compute stats
    def compute_stats(values):
        if not values:
            return {"n": 0, "values": [], "mean": None, "std": None}
        mean = sum(values) / len(values)
        if len(values) > 1:
            variance = sum((v - mean) ** 2 for v in values) / (len(values) - 1)
            std = math.sqrt(variance)
        else:
            std = 0.0
        return {"n": len(values), "values": values, "mean": mean, "std": std}

    results = {}
    for m in metric_names:
        results[m] = {
            "treatment": compute_stats(treatment_metric_values[m]),
            "baseline": compute_stats(baseline_metric_values[m]),
        }
        t = results[m]["treatment"]
        b = results[m]["baseline"]
        if t["mean"] is not None and b["mean"] is not None:
            results[m]["delta"] = t["mean"] - b["mean"]
        else:
            results[m]["delta"] = None

    # Determine missing runs
    missing = []
    a_list = sorted(a_stages)
    b_list = sorted(b_stages)
    if not found_treatment:
        missing.append({
            "condition": "treatment",
            "description": f"Need a run with {treatment_proto} on stages [{', '.join(a_list)}] and {baseline_proto} on stages [{', '.join(b_list)}]",
            "protocol_map": {s: treatment_proto for s in a_list} | {s: baseline_proto for s in b_list},
        })
    if not found_baseline:
        missing.append({
            "condition": "baseline",
            "description": f"Need a run with {baseline_proto} on all stages [{', '.join(sorted(a_stages | b_stages))}]",
            "protocol_map": {s: baseline_proto for s in sorted(a_stages | b_stages)},
        })

    return {
        "results": results,
        "missing": missing,
        "group_a": a_list,
        "group_b": b_list,
        "treatment_protocol": treatment_proto,
        "baseline_protocol": baseline_proto,
    }


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
  .tab-bar { background: #16213e; display: flex; gap: 0; border-bottom: 2px solid #0f3460; padding: 0 20px; }
  .tab-btn { padding: 8px 20px; font-size: 13px; font-weight: 500; color: #888; background: transparent; border: none; cursor: pointer; border-bottom: 2px solid transparent; margin-bottom: -2px; transition: all 0.2s; }
  .tab-btn:hover { color: #e0e0e0; }
  .tab-btn.active { color: #e94560; border-bottom-color: #e94560; }
  .tab-content { display: none; flex: 1; overflow: hidden; }
  .tab-content.active { display: flex; }
  .main { display: flex; flex: 1; overflow: hidden; }
  .sidebar-left { width: 280px; background: #16213e; border-right: 1px solid #0f3460; overflow-y: auto; padding: 12px; flex-shrink: 0; }
  .sidebar-right { width: 320px; background: #16213e; border-left: 1px solid #0f3460; overflow-y: auto; padding: 12px; flex-shrink: 0; }
  .terminal-area { flex: 1; display: flex; flex-direction: column; min-width: 0; }
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
  .btn-auto { background: #6366f1; color: #fff; }
  .btn-auto:hover { background: #4f46e5; }
  .btn-auto.active { background: #22c55e; color: #000; }
  .auto-status { font-size: 12px; color: #6366f1; margin-left: 8px; }
  .presence-active { background: #22c55e; color: #000; }
  .presence-away { background: #f59e0b; color: #000; }
  .section-title { font-size: 11px; text-transform: uppercase; color: #666; margin: 12px 0 6px; letter-spacing: 0.5px; }
  #xterm { width: 100%; height: 100%; }
  select { width: 100%; padding: 6px 8px; border-radius: 6px; border: 1px solid #0f3460; background: #1a1a2e; color: #e0e0e0; font-size: 13px; margin-bottom: 8px; }
  .proto-desc { font-size: 12px; color: #888; margin-bottom: 8px; min-height: 18px; }
  .btn-init { width: 100%; margin-bottom: 12px; }
  .info-panel { background: #1a1a2e; border-radius: 6px; padding: 10px; margin-bottom: 10px; font-size: 12px; line-height: 1.5; color: #ccc; white-space: pre-wrap; word-wrap: break-word; max-height: 250px; overflow-y: auto; }
  .info-panel.empty { color: #555; font-style: italic; }
  .stat-row { display: flex; justify-content: space-between; padding: 4px 0; font-size: 13px; border-bottom: 1px solid #0f3460; }
  .stat-label { color: #888; }
  .stat-value { color: #e0e0e0; font-weight: 500; font-variant-numeric: tabular-nums; }
  .stats-panel { background: #1a1a2e; border-radius: 6px; padding: 10px; margin-bottom: 10px; }
  /* Visualization tab styles */
  .viz-container { display: flex; flex: 1; overflow: hidden; }
  .viz-sidebar { width: 300px; background: #16213e; border-right: 1px solid #0f3460; overflow-y: auto; padding: 16px; flex-shrink: 0; }
  .viz-main { flex: 1; padding: 20px; overflow-y: auto; display: flex; flex-direction: column; }
  .viz-chart-wrap { flex: 1; min-height: 400px; position: relative; background: #1a1a2e; border-radius: 8px; padding: 12px; }
  .viz-chart-wrap canvas { width: 100% !important; height: 100% !important; }
  .viz-select { width: 100%; padding: 6px 8px; border-radius: 6px; border: 1px solid #0f3460; background: #1a1a2e; color: #e0e0e0; font-size: 13px; margin-bottom: 8px; }
  .viz-label { font-size: 11px; text-transform: uppercase; color: #666; margin: 10px 0 4px; letter-spacing: 0.5px; }
  .viz-checkbox-row { display: flex; align-items: center; gap: 8px; font-size: 13px; color: #ccc; padding: 3px 0; }
  .viz-checkbox-row input[type="checkbox"] { accent-color: #e94560; }
  .viz-btn { width: 100%; padding: 8px; border-radius: 6px; border: none; cursor: pointer; font-size: 13px; font-weight: 600; background: #e94560; color: #fff; margin-top: 12px; }
  .viz-btn:hover { background: #c73e54; }
  .viz-info { background: #1a1a2e; border-radius: 6px; padding: 12px; margin-top: 12px; font-size: 12px; color: #ccc; line-height: 1.6; }
  /* Differential tab styles */
  .diff-container { display: flex; flex: 1; overflow: hidden; }
  .diff-sidebar { width: 340px; background: #16213e; border-right: 1px solid #0f3460; overflow-y: auto; padding: 16px; flex-shrink: 0; }
  .diff-main { flex: 1; padding: 20px; overflow-y: auto; }
  .diff-stage-row { display: flex; align-items: center; gap: 6px; padding: 4px 0; font-size: 13px; }
  .diff-stage-name { flex: 1; color: #ccc; min-width: 120px; }
  .diff-radio-group { display: flex; gap: 12px; }
  .diff-radio-group label { display: flex; align-items: center; gap: 3px; font-size: 12px; color: #888; cursor: pointer; }
  .diff-radio-group input[type="radio"] { accent-color: #e94560; }
  .diff-result-card { background: #1a1a2e; border-radius: 8px; padding: 16px; margin-bottom: 12px; }
  .diff-result-header { font-size: 14px; font-weight: 600; color: #e94560; margin-bottom: 8px; }
  .diff-stat { display: flex; justify-content: space-between; padding: 4px 0; font-size: 13px; }
  .diff-stat .label { color: #888; }
  .diff-stat .value { color: #e0e0e0; font-weight: 500; }
  .diff-delta-positive { color: #4ade80; }
  .diff-delta-negative { color: #ef4444; }
  .diff-missing { background: #3b2020; border: 1px solid #7f1d1d; border-radius: 8px; padding: 14px; margin-top: 12px; }
  .diff-missing-title { color: #fca5a5; font-weight: 600; font-size: 13px; margin-bottom: 6px; }
  .diff-missing-item { color: #fca5a5; font-size: 12px; padding: 3px 0; }
  .diff-preset-bar { display: flex; flex-wrap: wrap; gap: 4px; margin: 8px 0; }
  .diff-preset-btn { padding: 3px 8px; font-size: 11px; border-radius: 4px; border: 1px solid #0f3460; background: #1a1a2e; color: #888; cursor: pointer; }
  .diff-preset-btn:hover { background: #0f3460; color: #e0e0e0; }
</style>
</head>
<body>
<header>
  <h1>Benchmark Experiment</h1>
  <span class="header-info" id="header-info">Select a protocol to begin</span>
</header>
<div class="tab-bar">
  <button class="tab-btn active" onclick="switchTab('experiment')">Experiment</button>
  <button class="tab-btn" onclick="switchTab('visualizer')">Results Visualizer</button>
  <button class="tab-btn" onclick="switchTab('differential')">Differential Analysis</button>
</div>
<!-- Tab: Experiment (default) -->
<div id="tab-experiment" class="tab-content active" style="flex-direction:column;flex:1;">
<div class="main" style="flex:1;">
  <div class="sidebar-left">
    <div class="section-title">Protocol</div>
    <select id="protocol-select" onchange="updateProtocolInfo()">
      <option value="">Loading...</option>
    </select>
    <div class="proto-desc" id="proto-desc"></div>
    <button class="btn-primary btn-init" id="btn-init" onclick="initExperiment()">Initialize Experiment</button>
    <div class="section-title">Stages</div>
    <div id="stage-list"></div>
  </div>
  <div class="terminal-area">
    <div class="terminal-container" id="terminal-container">
      <div id="xterm"></div>
    </div>
    <div class="controls">
      <button class="btn-primary" id="btn-start" onclick="startStage()" disabled>Start Stage</button>
      <button class="btn-primary" id="btn-complete" onclick="completeStage()" disabled>Stage Complete</button>
      <button class="btn-secondary" id="btn-skip" onclick="skipStage()" disabled>Skip</button>
      <span style="margin-left:16px;border-left:1px solid #0f3460;height:24px;"></span>
      <button class="btn-auto" id="btn-auto" onclick="toggleAutoMode()">Semi-Auto</button>
      <span class="auto-status" id="auto-status"></span>
      <span style="flex:1"></span>
      <button class="presence-active" id="btn-presence" onclick="togglePresence()">Active</button>
      <button class="btn-danger" onclick="abortExperiment()">Abort</button>
    </div>
  </div>
  <div class="sidebar-right">
    <div class="section-title">Live Stats</div>
    <div class="stats-panel" id="stats-panel">
      <div class="stat-row"><span class="stat-label">Status</span><span class="stat-value" id="stat-status">Not initialized</span></div>
      <div class="stat-row"><span class="stat-label">Wall Clock</span><span class="stat-value" id="stat-wall">--</span></div>
      <div class="stat-row"><span class="stat-label">Human Time</span><span class="stat-value" id="stat-human">--</span></div>
      <div class="stat-row"><span class="stat-label">Live Tokens</span><span class="stat-value" id="stat-tokens">--</span></div>
      <div class="stat-row"><span class="stat-label">Total Tokens</span><span class="stat-value" id="stat-cumul-tokens">0</span></div>
      <div class="stat-row"><span class="stat-label">Total Human Time</span><span class="stat-value" id="stat-cumul-human">0m 0s</span></div>
      <div class="stat-row"><span class="stat-label">Stages Done</span><span class="stat-value" id="stat-stages">0 / 0</span></div>
      <div class="stat-row"><span class="stat-label">PTY / Stage</span><span class="stat-value" id="stat-internal" style="font-size:11px;color:#666;">--</span></div>
    </div>
    <div class="section-title">Human Instructions</div>
    <div class="info-panel empty" id="panel-human-instructions">Select a protocol to see instructions</div>
    <div class="section-title">Added Instructions</div>
    <div class="info-panel empty" id="panel-added-instructions">Select a protocol to see added instructions</div>
    <div class="section-title">Planning Prompt</div>
    <div class="info-panel empty" id="panel-planning-prompt">Select a protocol to see planning prompt</div>
    <div class="section-title">Experiment Tree</div>
    <div class="info-panel" id="panel-tree" style="font-size:11px; font-family:monospace;">Loading...</div>
    <div class="section-title">Comparisons</div>
    <div class="info-panel" id="panel-comparisons" style="font-size:11px;">Loading...</div>
    <button class="btn-secondary" style="width:100%;margin-top:6px;" onclick="showForkDialog()">Fork from Node...</button>
    <div class="section-title">Harness Log</div>
    <div class="info-panel" id="panel-harness-log" style="font-size:10px; font-family:monospace; max-height:200px; overflow-y:auto; color:#888;"></div>
  </div>
</div>
</div><!-- end tab-experiment -->

<!-- Tab: Results Visualizer -->
<div id="tab-visualizer" class="tab-content">
  <div class="viz-container">
    <div class="viz-sidebar">
      <div class="viz-label">Task</div>
      <select class="viz-select" id="viz-task" onchange="vizTaskChanged()">
        <option value="">All Tasks</option>
      </select>

      <div class="viz-label">Metric</div>
      <select class="viz-select" id="viz-metric">
        <option value="holdout_accuracy">Holdout Accuracy</option>
        <option value="training_accuracy">Training Accuracy</option>
        <option value="regression_rate">Regression Rate</option>
        <option value="wall_time_seconds">Wall Time (s)</option>
        <option value="human_time_seconds">Human Time (s)</option>
        <option value="output_tokens">Output Tokens</option>
        <option value="effective_tokens">Effective Tokens</option>
        <option value="total_tokens">Total Tokens</option>
        <option value="code_lines">Code Lines</option>
        <option value="input_tokens">Input Tokens</option>
        <option value="cache_creation_tokens">Cache Write Tokens</option>
        <option value="cache_read_tokens">Cache Read Tokens</option>
      </select>

      <div class="viz-label">Group Bars By</div>
      <select class="viz-select" id="viz-groupby">
        <option value="stage">By Stage (bars = protocols)</option>
        <option value="protocol">By Protocol (bars = stages)</option>
      </select>

      <div class="viz-label">View Mode</div>
      <select class="viz-select" id="viz-viewmode">
        <option value="single">Per-Stage Detail</option>
        <option value="cumulative">Cumulative / Summary</option>
      </select>

      <div class="viz-label" style="margin-top:14px;">Options</div>
      <div class="viz-checkbox-row">
        <input type="checkbox" id="viz-errorbars" checked>
        <label for="viz-errorbars">Show error bars (multi-run)</label>
      </div>
      <div class="viz-checkbox-row">
        <input type="checkbox" id="viz-coalesce">
        <label for="viz-coalesce">Coalesce by stage tags</label>
      </div>

      <button class="viz-btn" onclick="renderVizChart()">Update Chart</button>

      <div class="viz-info" id="viz-info">
        Load data and click Update Chart to visualize results.
      </div>
    </div>
    <div class="viz-main">
      <div class="viz-chart-wrap">
        <canvas id="viz-chart"></canvas>
      </div>
    </div>
  </div>
</div>

<!-- Tab: Differential Analysis -->
<div id="tab-differential" class="tab-content">
  <div class="diff-container">
    <div class="diff-sidebar">
      <div class="viz-label">Task</div>
      <select class="viz-select" id="diff-task" onchange="diffTaskChanged()">
        <option value="">Select a task...</option>
      </select>

      <div class="viz-label">Treatment Protocol</div>
      <select class="viz-select" id="diff-treatment"></select>

      <div class="viz-label">Baseline Protocol</div>
      <select class="viz-select" id="diff-baseline"></select>

      <div class="viz-label">Metrics</div>
      <div id="diff-metric-checkboxes">
        <div class="viz-checkbox-row"><input type="checkbox" value="holdout_accuracy" checked><label>Holdout Accuracy</label></div>
        <div class="viz-checkbox-row"><input type="checkbox" value="training_accuracy"><label>Training Accuracy</label></div>
        <div class="viz-checkbox-row"><input type="checkbox" value="regression_rate"><label>Regression Rate</label></div>
        <div class="viz-checkbox-row"><input type="checkbox" value="effective_tokens"><label>Effective Tokens</label></div>
        <div class="viz-checkbox-row"><input type="checkbox" value="wall_time_seconds"><label>Wall Time</label></div>
        <div class="viz-checkbox-row"><input type="checkbox" value="code_lines"><label>Code Lines</label></div>
      </div>

      <div class="viz-label" style="margin-top:14px;">Stage Groups</div>
      <div class="diff-preset-bar" id="diff-presets"></div>
      <div id="diff-stage-selector"></div>

      <button class="viz-btn" onclick="runDifferential()">Analyze</button>
    </div>
    <div class="diff-main" id="diff-results">
      <div class="diff-result-card">
        <div style="color:#888;font-size:13px;">Select a task, configure groups A and B, then click Analyze.</div>
        <div style="color:#666;font-size:12px;margin-top:8px;">
          Group A = stages where the treatment protocol is applied.<br>
          Group B = stages where the baseline protocol is applied (measurement point).<br><br>
          The differential compares:<br>
          Treatment: treatment on A, baseline on B<br>
          vs. Baseline: baseline on all of A+B<br><br>
          The effect is measured on the B stages.
        </div>
      </div>
    </div>
  </div>
</div>

<!-- Fork dialog -->
<div id="fork-dialog" style="display:none; position:fixed; top:50%; left:50%; transform:translate(-50%,-50%); background:#16213e; border:1px solid #0f3460; border-radius:10px; padding:20px; z-index:1000; min-width:380px;">
  <h3 style="margin-bottom:12px; color:#e94560;">Fork from Existing State</h3>
  <label style="font-size:13px;color:#888;">Node ID:</label>
  <input id="fork-node-id" style="width:100%;padding:6px;border-radius:6px;border:1px solid #0f3460;background:#1a1a2e;color:#e0e0e0;margin-bottom:8px;" placeholder="e.g. node_001">
  <label style="font-size:13px;color:#888;">Protocol:</label>
  <select id="fork-protocol" style="width:100%;padding:6px;border-radius:6px;border:1px solid #0f3460;background:#1a1a2e;color:#e0e0e0;margin-bottom:8px;"></select>
  <label style="font-size:13px;color:#888;">Pipeline (optional):</label>
  <select id="fork-pipeline" style="width:100%;padding:6px;border-radius:6px;border:1px solid #0f3460;background:#1a1a2e;color:#e0e0e0;margin-bottom:12px;">
    <option value="">None</option>
  </select>
  <div style="display:flex;gap:8px;">
    <button class="btn-primary" onclick="executeFork()">Fork</button>
    <button class="btn-secondary" onclick="document.getElementById('fork-dialog').style.display='none'">Cancel</button>
  </div>
</div>

<script src="https://cdn.jsdelivr.net/npm/@xterm/xterm@5/lib/xterm.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/@xterm/addon-fit@0.10/lib/addon-fit.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4/dist/chart.umd.min.js"></script>
<script>
  let term = null;
  let termWs = null;
  let resizeWs = null;
  let fitAddon = null;
  let dataDisposable = null;
  let resizeDisposable = null;
  let lastPtyActive = false;
  let lastStageIdx = -1;
  let protocolsData = [];

  // Visualization state
  let vizChart = null;
  let vizLogsData = null;
  let vizTasksData = null;
  let diffChart = null;

  function switchTab(tabId) {
    document.querySelectorAll('.tab-content').forEach(el => el.classList.remove('active'));
    document.querySelectorAll('.tab-btn').forEach(el => el.classList.remove('active'));
    const tab = document.getElementById('tab-' + tabId);
    if (tab) tab.classList.add('active');
    // Activate the button
    const buttons = document.querySelectorAll('.tab-btn');
    const tabNames = ['experiment', 'visualizer', 'differential'];
    const idx = tabNames.indexOf(tabId);
    if (idx >= 0 && buttons[idx]) buttons[idx].classList.add('active');
    // Resize terminal when switching back to experiment tab
    if (tabId === 'experiment' && fitAddon) {
      setTimeout(() => fitAddon.fit(), 50);
    }
    // Load viz data when switching to visualizer or differential
    if (tabId === 'visualizer' || tabId === 'differential') {
      loadVizData();
    }
  }

  function formatDuration(seconds) {
    if (seconds == null || isNaN(seconds)) return '--';
    const m = Math.floor(seconds / 60);
    const s = Math.floor(seconds % 60);
    return m > 0 ? `${m}m ${s}s` : `${s}s`;
  }

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
    term.writeln('Select a protocol and click "Initialize Experiment" to begin.\\r\\n');

    window.addEventListener('resize', () => fitAddon.fit());
  }

  async function loadProtocols() {
    const res = await fetch('/api/protocols');
    const data = await res.json();
    protocolsData = data.protocols;
    const select = document.getElementById('protocol-select');
    select.innerHTML = '';
    protocolsData.forEach(p => {
      const opt = document.createElement('option');
      opt.value = p.name;
      opt.textContent = p.name;
      select.appendChild(opt);
    });
    // Pre-select default if provided
    if (data.default && protocolsData.some(p => p.name === data.default)) {
      select.value = data.default;
    }
    updateProtocolInfo();
  }

  function updateProtocolInfo() {
    const name = document.getElementById('protocol-select').value;
    const proto = protocolsData.find(p => p.name === name);
    document.getElementById('proto-desc').textContent = proto ? proto.description : '';

    const setPanel = (id, text) => {
      const el = document.getElementById(id);
      if (text && text.trim()) {
        el.textContent = text.trim();
        el.className = 'info-panel';
      } else {
        el.textContent = 'None';
        el.className = 'info-panel empty';
      }
    };
    setPanel('panel-human-instructions', proto ? proto.human_instructions : '');
    setPanel('panel-added-instructions', proto ? proto.added_instructions : '');
    setPanel('panel-planning-prompt', proto ? proto.planning_prompt : '');
  }

  async function initExperiment() {
    const protocol = document.getElementById('protocol-select').value;
    if (!protocol) return;
    document.getElementById('btn-init').disabled = true;
    document.getElementById('btn-init').textContent = 'Initializing...';
    term.clear();
    term.writeln(`Initializing experiment with protocol: ${protocol}...\\r\\n`);
    const res = await fetch('/api/experiment/init', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({protocol}),
    });
    const data = await res.json();
    document.getElementById('btn-init').disabled = false;
    document.getElementById('btn-init').textContent = 'Initialize Experiment';
    if (data.error) {
      term.writeln('Error: ' + data.error);
      return;
    }
    term.writeln(`Run ID: ${data.run_id}`);
    term.writeln(`Stages: ${data.stages.join(', ')}\\r\\n`);
    term.writeln('Click "Start Stage" to begin.\\r\\n');
    refreshState();
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
    try {
      const res = await fetch('/api/state');
      const data = await res.json();

      // Header info
      if (data.initialized) {
        document.getElementById('header-info').textContent =
          `Protocol: ${data.protocol || '?'} | Model: ${data.model || '?'}`;
      }

      // Stage list
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

      // Button states
      const hasActive = data.current_stage_idx >= 0;
      const allDone = data.stages.length > 0 && data.stages.every(s => s.status === 'completed' || s.metrics?.skipped);
      document.getElementById('btn-start').disabled = !data.initialized || hasActive || allDone;
      document.getElementById('btn-complete').disabled = !hasActive;
      document.getElementById('btn-skip').disabled = !data.initialized || allDone;

      const btn = document.getElementById('btn-presence');
      btn.textContent = data.presence_status === 'active' ? 'Active' : 'Away';
      btn.className = data.presence_status === 'active' ? 'presence-active' : 'presence-away';

      // Live stats
      const completed = data.stages.filter(s => s.status === 'completed').length;
      const total = data.stages.length;
      document.getElementById('stat-stages').textContent = `${completed} / ${total}`;
      document.getElementById('stat-cumul-tokens').textContent = (data.cumulative_tokens || 0).toLocaleString();
      document.getElementById('stat-cumul-human').textContent = formatDuration(data.cumulative_human_time || 0);
      document.getElementById('stat-internal').textContent =
        `pty=${data.pty_active ? 'yes' : 'no'} idx=${data.current_stage_idx} auto=${data.auto_status || 'off'}`;

      if (data.live_stats) {
        let statusText = 'Stage in progress';
        if (data.auto_status === 'running') statusText = 'Auto: Claude running...';
        else if (data.auto_status === 'completing') statusText = 'Auto: collecting metrics...';
        else if (data.auto_status === 'advancing') statusText = 'Auto: starting next stage...';
        document.getElementById('stat-status').textContent = statusText;
        document.getElementById('stat-status').style.color = data.auto_status ? '#6366f1' : '#e94560';
        document.getElementById('stat-wall').textContent = formatDuration(data.live_stats.wall_elapsed_seconds);
        document.getElementById('stat-human').textContent = formatDuration(data.live_stats.human_time_seconds);
        document.getElementById('stat-tokens').textContent = (data.live_stats.live_tokens || 0).toLocaleString();
      } else if (data.initialized) {
        document.getElementById('stat-status').textContent = allDone ? 'Complete' : 'Idle';
        document.getElementById('stat-status').style.color = allDone ? '#4ade80' : '#888';
        document.getElementById('stat-wall').textContent = '--';
        document.getElementById('stat-human').textContent = '--';
        document.getElementById('stat-tokens').textContent = '--';
      }

      // Update auto mode UI
      const autoBtn = document.getElementById('btn-auto');
      autoBtn.classList.toggle('active', data.auto_mode);
      autoBtn.textContent = data.auto_mode ? 'Semi-Auto: ON' : 'Semi-Auto';
      const autoStatusEl = document.getElementById('auto-status');
      const autoStatusMap = {running: 'Claude running...', completing: 'Collecting metrics...', advancing: 'Starting next stage...'};
      autoStatusEl.textContent = data.auto_status ? autoStatusMap[data.auto_status] || '' : '';

      // Harness log
      const logPanel = document.getElementById('panel-harness-log');
      if (data.harness_log && data.harness_log.length > 0) {
        logPanel.innerHTML = data.harness_log.map(l =>
          `<div>${l.replace(/</g,'&lt;')}</div>`
        ).join('');
        logPanel.scrollTop = logPanel.scrollHeight;
      } else {
        logPanel.innerHTML = '<div style="color:#555;font-style:italic;">No log entries</div>';
      }

      // Auto-reconnect terminal if WebSocket is fully dead (CLOSED) and a PTY is active.
      // Don't reconnect if WS is CONNECTING (readyState 0) — it's still being set up.
      const wsDead = !termWs || termWs.readyState === WebSocket.CLOSED || termWs.readyState === WebSocket.CLOSING;
      if (data.pty_active && wsDead && data.current_stage_idx >= 0) {
        const stageId = data.stages[data.current_stage_idx]?.id || '?';
        term.writeln(`\\r\\n--- Reconnecting to stage: ${stageId} ---\\r\\n`);
        connectTerminal();
      }
      lastPtyActive = data.pty_active;
      lastStageIdx = data.current_stage_idx;
    } catch(e) {
      // Silently ignore fetch errors (e.g., server restart)
    }
  }

  async function startStage() {
    term.clear();
    const res = await fetch('/api/stage/start', {method: 'POST'});
    const data = await res.json();
    if (data.error) { term.writeln('Error: ' + data.error); return; }
    term.writeln(`Starting stage: ${data.stage_id}\\r\\n`);
    // Update tracking vars BEFORE connectTerminal so refreshState poll doesn't re-trigger
    lastPtyActive = true;
    lastStageIdx = data.stage_idx;
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

  async function toggleAutoMode() {
    const btn = document.getElementById('btn-auto');
    const isActive = btn.classList.contains('active');
    const newMode = !isActive;
    const res = await fetch('/api/auto/configure', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({auto_mode: newMode, auto_advance: newMode}),
    });
    const data = await res.json();
    btn.classList.toggle('active', data.auto_mode);
    btn.textContent = data.auto_mode ? 'Semi-Auto: ON' : 'Semi-Auto';
    refreshState();
  }

  async function abortExperiment() {
    if (!confirm('Abort the experiment? Progress will be saved.')) return;
    await fetch('/api/experiment/abort', {method: 'POST'});
    term.writeln('\\r\\nExperiment aborted. Log saved.');
    refreshState();
  }

  async function loadTree() {
    try {
      const res = await fetch('/api/tree');
      const data = await res.json();
      const panel = document.getElementById('panel-tree');
      const nodes = data.nodes || {};
      const ids = Object.keys(nodes).sort();
      if (ids.length === 0) {
        panel.textContent = 'No experiment history yet.';
        panel.className = 'info-panel empty';
        return;
      }
      let html = '';
      ids.forEach(id => {
        const n = nodes[id];
        const parent = n.parent ? ` ← ${n.parent}` : ' (root)';
        html += `<div style="margin-bottom:3px;"><span style="color:#e94560;">${id}</span> ${n.stage_id} <span style="color:#888;">[${n.protocol}]</span>${parent}</div>`;
      });
      panel.innerHTML = html;
      panel.className = 'info-panel';
    } catch(e) {}
  }

  async function loadComparisons() {
    try {
      const res = await fetch('/api/comparisons/available');
      const data = await res.json();
      const panel = document.getElementById('panel-comparisons');
      let html = '';
      if (data.available.length > 0) {
        html += '<div style="color:#4ade80;margin-bottom:4px;">Available:</div>';
        data.available.forEach(c => {
          html += `<div style="margin-left:8px;">${c.stage_id}: ${c.protocols.join(' vs ')}</div>`;
        });
      }
      if (data.missing.length > 0) {
        html += '<div style="color:#f59e0b;margin-top:6px;margin-bottom:4px;">Missing:</div>';
        data.missing.slice(0, 10).forEach(m => {
          html += `<div style="margin-left:8px;">${m.stage_id} [${m.protocol}]</div>`;
        });
        if (data.missing.length > 10) html += `<div style="margin-left:8px;color:#888;">...and ${data.missing.length - 10} more</div>`;
      }
      if (!html) html = 'No data yet.';
      panel.innerHTML = html;
      panel.className = 'info-panel';
    } catch(e) {}
  }

  async function showForkDialog() {
    const dialog = document.getElementById('fork-dialog');
    // Populate protocol select
    const sel = document.getElementById('fork-protocol');
    sel.innerHTML = '';
    protocolsData.forEach(p => {
      const opt = document.createElement('option');
      opt.value = p.name; opt.textContent = p.name;
      sel.appendChild(opt);
    });
    // Populate pipeline select
    try {
      const res = await fetch('/api/pipelines');
      const data = await res.json();
      const pipSel = document.getElementById('fork-pipeline');
      pipSel.innerHTML = '<option value="">None</option>';
      Object.keys(data.pipelines || {}).forEach(name => {
        const opt = document.createElement('option');
        opt.value = name; opt.textContent = name;
        pipSel.appendChild(opt);
      });
    } catch(e) {}
    dialog.style.display = 'block';
  }

  async function executeFork() {
    const nodeId = document.getElementById('fork-node-id').value.trim();
    const protocol = document.getElementById('fork-protocol').value;
    const pipeline = document.getElementById('fork-pipeline').value;
    if (!nodeId) { alert('Enter a node ID'); return; }
    document.getElementById('fork-dialog').style.display = 'none';
    term.clear();
    term.writeln(`Forking from ${nodeId} with protocol ${protocol}...\\r\\n`);
    const body = {node_id: nodeId, protocol: protocol};
    if (pipeline) body.pipeline = pipeline;
    const res = await fetch('/api/experiment/fork', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(body),
    });
    const data = await res.json();
    if (data.error) { term.writeln('Error: ' + data.error); return; }
    term.writeln(`Forked! Run ID: ${data.run_id}`);
    term.writeln(`Completed stages: ${data.completed_stages.join(', ')}`);
    term.writeln(`Remaining stages: ${data.stages.filter(s => !data.completed_stages.includes(s)).join(', ')}\\r\\n`);
    refreshState();
    loadTree();
    loadComparisons();
  }

  // ---- Results Visualizer ----

  const VIZ_COLORS = [
    '#e94560', '#3b82f6', '#22c55e', '#f59e0b', '#a78bfa',
    '#06b6d4', '#f472b6', '#84cc16', '#fb923c', '#818cf8'
  ];

  async function loadVizData() {
    if (vizLogsData && vizTasksData) return; // already loaded
    try {
      const [logsRes, tasksRes] = await Promise.all([
        fetch('/api/logs'), fetch('/api/tasks')
      ]);
      vizLogsData = (await logsRes.json()).runs || [];
      vizTasksData = (await tasksRes.json()).tasks || {};
      populateVizSelectors();
      populateDiffSelectors();
    } catch(e) {
      console.error('Failed to load viz data:', e);
    }
  }

  function populateVizSelectors() {
    // Task selector
    const taskSel = document.getElementById('viz-task');
    taskSel.innerHTML = '<option value="">All Tasks</option>';
    const taskNames = new Set();
    vizLogsData.forEach(r => { if (r.task) taskNames.add(r.task); });
    Object.keys(vizTasksData).forEach(t => taskNames.add(t));
    [...taskNames].sort().forEach(t => {
      const opt = document.createElement('option');
      opt.value = t;
      const name = vizTasksData[t]?.name || t.split('/').pop();
      opt.textContent = name;
      taskSel.appendChild(opt);
    });
  }

  function vizTaskChanged() {
    // No special action needed; chart re-renders on button click
  }

  function getStageTag(taskPath, stageId) {
    const task = vizTasksData[taskPath];
    if (!task) return null;
    const stage = task.stages.find(s =>
      stageId === s.id || stageId.endsWith('_' + s.id)
    );
    if (stage && stage.pipeline_tags && stage.pipeline_tags.length > 0) {
      return stage.pipeline_tags.join(', ');
    }
    return null;
  }

  function renderVizChart() {
    if (!vizLogsData) { alert('No data loaded yet.'); return; }

    const metric = document.getElementById('viz-metric').value;
    const groupBy = document.getElementById('viz-groupby').value;
    const viewMode = document.getElementById('viz-viewmode').value;
    const showErrors = document.getElementById('viz-errorbars').checked;
    const coalesce = document.getElementById('viz-coalesce').checked;
    const taskFilter = document.getElementById('viz-task').value;

    // Filter runs by task
    let runs = vizLogsData;
    if (taskFilter) {
      runs = runs.filter(r => {
        const rt = (r.task || '').replace(/\\/$/, '');
        return rt === taskFilter || rt.endsWith('/' + taskFilter.split('/').pop());
      });
    }

    if (runs.length === 0) {
      document.getElementById('viz-info').textContent = 'No matching runs found.';
      return;
    }

    // Collect all protocols and stages
    const protocols = [...new Set(runs.map(r => r.protocol))].sort();
    let stageIds = [];
    runs.forEach(r => {
      (r.stages || []).forEach(s => {
        if (!stageIds.includes(s.stage_id)) stageIds.push(s.stage_id);
      });
    });

    // Build data index: {protocol -> {stage_id -> [values]}}
    const dataIndex = {};
    protocols.forEach(p => { dataIndex[p] = {}; });
    runs.forEach(r => {
      const proto = r.protocol;
      (r.stages || []).forEach(s => {
        const val = s[metric];
        if (val == null) return;
        if (!dataIndex[proto][s.stage_id]) dataIndex[proto][s.stage_id] = [];
        dataIndex[proto][s.stage_id].push(val);
      });
    });

    // Handle coalescing by stage tags
    let labelMap = {}; // stageId -> display label
    if (coalesce && taskFilter) {
      const tagGroups = {}; // tag -> [stageIds]
      stageIds.forEach(sid => {
        const tag = getStageTag(taskFilter, sid) || sid;
        if (!tagGroups[tag]) tagGroups[tag] = [];
        tagGroups[tag].push(sid);
      });
      // Merge stage values under tag labels
      const newDataIndex = {};
      protocols.forEach(p => {
        newDataIndex[p] = {};
        Object.entries(tagGroups).forEach(([tag, sids]) => {
          const merged = [];
          sids.forEach(sid => {
            (dataIndex[p][sid] || []).forEach(v => merged.push(v));
          });
          if (merged.length > 0) newDataIndex[p][tag] = merged;
        });
      });
      stageIds = Object.keys(tagGroups);
      Object.assign(dataIndex, newDataIndex);
    }

    // Compute mean and std for each cell
    function stats(arr) {
      if (!arr || arr.length === 0) return { mean: 0, std: 0, n: 0 };
      const mean = arr.reduce((a, b) => a + b, 0) / arr.length;
      if (arr.length < 2) return { mean, std: 0, n: arr.length };
      const variance = arr.reduce((a, b) => a + (b - mean) ** 2, 0) / (arr.length - 1);
      return { mean, std: Math.sqrt(variance), n: arr.length };
    }

    let labels, datasets;

    if (viewMode === 'cumulative') {
      // Cumulative: one bar per protocol, aggregated across stages
      labels = protocols;
      const isRate = ['holdout_accuracy', 'training_accuracy', 'regression_rate'].includes(metric);
      const values = [];
      const errors = [];
      protocols.forEach(p => {
        // Collect all values across all stages for this protocol
        const allVals = [];
        stageIds.forEach(sid => {
          (dataIndex[p][sid] || []).forEach(v => allVals.push(v));
        });
        if (isRate) {
          // For rates, compute mean of means per run
          const s = stats(allVals);
          values.push(s.mean);
          errors.push(showErrors ? s.std : 0);
        } else {
          // For absolute values, sum per run then average across runs
          // Group by run
          const perRun = {};
          runs.filter(r => r.protocol === p).forEach(r => {
            let total = 0;
            (r.stages || []).forEach(s => {
              if (s[metric] != null) total += s[metric];
            });
            perRun[r.run_id] = total;
          });
          const runTotals = Object.values(perRun);
          const s = stats(runTotals);
          values.push(s.mean);
          errors.push(showErrors ? s.std : 0);
        }
      });
      datasets = [{
        label: metric,
        data: values,
        backgroundColor: VIZ_COLORS.slice(0, protocols.length),
        borderColor: VIZ_COLORS.slice(0, protocols.length),
        borderWidth: 1,
      }];
      if (showErrors) {
        datasets[0].errorBars = errors;
      }
    } else if (groupBy === 'stage') {
      // X-axis = stages, one dataset per protocol
      labels = stageIds.map(s => s.replace(/^\\d+_/, ''));
      datasets = protocols.map((proto, pi) => {
        const values = stageIds.map(sid => stats(dataIndex[proto]?.[sid]).mean);
        const errs = stageIds.map(sid => stats(dataIndex[proto]?.[sid]).std);
        return {
          label: proto,
          data: values,
          backgroundColor: VIZ_COLORS[pi % VIZ_COLORS.length] + 'cc',
          borderColor: VIZ_COLORS[pi % VIZ_COLORS.length],
          borderWidth: 1,
          errorBars: showErrors ? errs : null,
        };
      });
    } else {
      // X-axis = protocols, one dataset per stage
      labels = protocols;
      datasets = stageIds.map((sid, si) => {
        const values = protocols.map(p => stats(dataIndex[p]?.[sid]).mean);
        const errs = protocols.map(p => stats(dataIndex[p]?.[sid]).std);
        return {
          label: sid.replace(/^\\d+_/, ''),
          data: values,
          backgroundColor: VIZ_COLORS[si % VIZ_COLORS.length] + 'cc',
          borderColor: VIZ_COLORS[si % VIZ_COLORS.length],
          borderWidth: 1,
          errorBars: showErrors ? errs : null,
        };
      });
    }

    // Render chart
    const ctx = document.getElementById('viz-chart').getContext('2d');
    if (vizChart) vizChart.destroy();

    // Error bar plugin
    const errorBarPlugin = {
      id: 'errorBars',
      afterDatasetsDraw(chart) {
        const { ctx: c, scales: { x, y } } = chart;
        chart.data.datasets.forEach((ds, di) => {
          if (!ds.errorBars) return;
          const meta = chart.getDatasetMeta(di);
          meta.data.forEach((bar, i) => {
            const err = ds.errorBars[i];
            if (!err || err === 0) return;
            const xPos = bar.x;
            const yVal = ds.data[i];
            const yTop = y.getPixelForValue(yVal + err);
            const yBot = y.getPixelForValue(yVal - err);
            const capW = bar.width ? bar.width * 0.3 : 6;
            c.save();
            c.strokeStyle = '#e0e0e0';
            c.lineWidth = 1.5;
            c.beginPath();
            c.moveTo(xPos, yTop);
            c.lineTo(xPos, yBot);
            c.moveTo(xPos - capW, yTop);
            c.lineTo(xPos + capW, yTop);
            c.moveTo(xPos - capW, yBot);
            c.lineTo(xPos + capW, yBot);
            c.stroke();
            c.restore();
          });
        });
      }
    };

    vizChart = new Chart(ctx, {
      type: 'bar',
      data: { labels, datasets },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { labels: { color: '#ccc' } },
          title: {
            display: true,
            text: `${metric} ${viewMode === 'cumulative' ? '(cumulative)' : ''} ${coalesce ? '[coalesced by tags]' : ''}`,
            color: '#e0e0e0',
            font: { size: 14 },
          },
        },
        scales: {
          x: { ticks: { color: '#888', maxRotation: 45 }, grid: { color: '#0f3460' } },
          y: { ticks: { color: '#888' }, grid: { color: '#0f3460' }, beginAtZero: true },
        },
      },
      plugins: [errorBarPlugin],
    });

    // Update info panel
    const totalRuns = runs.length;
    const multiRun = protocols.some(p =>
      stageIds.some(sid => (dataIndex[p]?.[sid]?.length || 0) > 1)
    );
    document.getElementById('viz-info').textContent =
      `${totalRuns} runs, ${protocols.length} protocols, ${stageIds.length} stages` +
      (multiRun ? ' (multi-run data available)' : '');
  }

  // ---- Differential Analysis ----

  function populateDiffSelectors() {
    // Task selector
    const taskSel = document.getElementById('diff-task');
    taskSel.innerHTML = '<option value="">Select a task...</option>';
    Object.entries(vizTasksData).forEach(([path, cfg]) => {
      const opt = document.createElement('option');
      opt.value = path;
      opt.textContent = cfg.name || path.split('/').pop();
      taskSel.appendChild(opt);
    });

    // Protocol selectors
    const protocols = [...new Set(vizLogsData.map(r => r.protocol))].sort();
    ['diff-treatment', 'diff-baseline'].forEach(selId => {
      const sel = document.getElementById(selId);
      sel.innerHTML = '';
      protocols.forEach(p => {
        const opt = document.createElement('option');
        opt.value = p; opt.textContent = p;
        sel.appendChild(opt);
      });
    });
    // Default baseline to first protocol if multiple
    if (protocols.length >= 2) {
      document.getElementById('diff-treatment').value = protocols[1] || protocols[0];
      document.getElementById('diff-baseline').value = protocols[0];
    }
  }

  function diffTaskChanged() {
    const taskPath = document.getElementById('diff-task').value;
    const task = vizTasksData[taskPath];
    const container = document.getElementById('diff-stage-selector');
    const presets = document.getElementById('diff-presets');
    container.innerHTML = '';
    presets.innerHTML = '';

    if (!task || !task.stages || task.stages.length === 0) {
      container.innerHTML = '<div style="color:#666;font-size:12px;">No stages found.</div>';
      return;
    }

    // Create stage radio buttons
    task.stages.forEach((stage, idx) => {
      const row = document.createElement('div');
      row.className = 'diff-stage-row';
      const name = `stage_group_${idx}`;
      row.innerHTML = `
        <span class="diff-stage-name">${idx + 1}. ${stage.id}</span>
        <div class="diff-radio-group">
          <label><input type="radio" name="${name}" value="a"> A</label>
          <label><input type="radio" name="${name}" value="b"> B</label>
          <label><input type="radio" name="${name}" value="" checked> --</label>
        </div>
      `;
      container.appendChild(row);
    });

    // Generate preset buttons: A={1..k};B={k+1} for each valid split
    const n = task.stages.length;
    for (let k = 1; k < n; k++) {
      const aStages = Array.from({length: k}, (_, i) => i + 1).join(',');
      const bStage = k + 1;
      const btn = document.createElement('button');
      btn.className = 'diff-preset-btn';
      btn.textContent = `A={${aStages}};B={${bStage}}`;
      btn.onclick = () => applyDiffPreset(k, k);
      presets.appendChild(btn);
    }
  }

  function applyDiffPreset(aEnd, bStart) {
    const task = vizTasksData[document.getElementById('diff-task').value];
    if (!task) return;
    task.stages.forEach((_, idx) => {
      const radios = document.querySelectorAll(`input[name="stage_group_${idx}"]`);
      radios.forEach(r => {
        if (idx < aEnd && r.value === 'a') r.checked = true;
        else if (idx === bStart && r.value === 'b') r.checked = true;
        else if (idx >= aEnd && idx !== bStart && r.value === '') r.checked = true;
        else if (idx < aEnd && r.value !== 'a') r.checked = false;
        else if (idx === bStart && r.value !== 'b') r.checked = false;
      });
    });
  }

  async function runDifferential() {
    const taskPath = document.getElementById('diff-task').value;
    const treatment = document.getElementById('diff-treatment').value;
    const baseline = document.getElementById('diff-baseline').value;

    if (!taskPath) { alert('Select a task first.'); return; }
    if (treatment === baseline) { alert('Treatment and baseline must be different protocols.'); return; }

    const task = vizTasksData[taskPath];
    const groupA = [];
    const groupB = [];

    task.stages.forEach((_, idx) => {
      const selected = document.querySelector(`input[name="stage_group_${idx}"]:checked`);
      if (selected && selected.value === 'a') groupA.push(idx);
      else if (selected && selected.value === 'b') groupB.push(idx);
    });

    if (groupA.length === 0 || groupB.length === 0) {
      alert('Assign at least one stage to group A and one to group B.');
      return;
    }

    // Get selected metrics
    const metrics = [];
    document.querySelectorAll('#diff-metric-checkboxes input[type="checkbox"]:checked').forEach(cb => {
      metrics.push(cb.value);
    });
    if (metrics.length === 0) { alert('Select at least one metric.'); return; }

    const resultsDiv = document.getElementById('diff-results');
    resultsDiv.innerHTML = '<div class="diff-result-card"><div style="color:#888;">Analyzing...</div></div>';

    try {
      const res = await fetch('/api/differential/analyze', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
          task: taskPath,
          group_a: groupA,
          group_b: groupB,
          treatment: treatment,
          baseline: baseline,
          metrics: metrics,
        }),
      });
      const data = await res.json();
      if (data.error) {
        resultsDiv.innerHTML = `<div class="diff-result-card"><div style="color:#ef4444;">${data.error}</div></div>`;
        return;
      }
      renderDiffResults(data);
    } catch(e) {
      resultsDiv.innerHTML = `<div class="diff-result-card"><div style="color:#ef4444;">Request failed: ${e.message}</div></div>`;
    }
  }

  function renderDiffResults(data) {
    const resultsDiv = document.getElementById('diff-results');
    let html = '';

    // Summary card
    const aStr = data.group_a.join(', ');
    const bStr = data.group_b.join(', ');
    html += `<div class="diff-result-card">
      <div class="diff-result-header">Differential: ${data.treatment_protocol} vs ${data.baseline_protocol}</div>
      <div class="diff-stat"><span class="label">Group A (treatment)</span><span class="value">${aStr}</span></div>
      <div class="diff-stat"><span class="label">Group B (measured)</span><span class="value">${bStr}</span></div>
    </div>`;

    // Per-metric results
    const metricNames = Object.keys(data.results || {});
    metricNames.forEach(metric => {
      const r = data.results[metric];
      const t = r.treatment;
      const b = r.baseline;
      const hasTreatment = t.mean !== null && t.mean !== undefined;
      const hasBaseline = b.mean !== null && b.mean !== undefined;

      html += `<div class="diff-result-card">
        <div class="diff-result-header">${metric}</div>`;

      if (hasTreatment && hasBaseline) {
        const delta = r.delta;
        const deltaStr = delta > 0 ? `+${delta.toFixed(4)}` : delta.toFixed(4);
        const deltaClass = delta > 0 ? 'diff-delta-positive' : (delta < 0 ? 'diff-delta-negative' : '');
        const isGoodPositive = ['holdout_accuracy', 'training_accuracy'].includes(metric);
        const isGoodNegative = ['regression_rate', 'effective_tokens', 'wall_time_seconds', 'human_time_seconds', 'code_lines'].includes(metric);

        html += `
          <div class="diff-stat"><span class="label">Treatment (n=${t.n})</span><span class="value">${t.mean.toFixed(4)} \\u00b1 ${t.std.toFixed(4)}</span></div>
          <div class="diff-stat"><span class="label">Baseline (n=${b.n})</span><span class="value">${b.mean.toFixed(4)} \\u00b1 ${b.std.toFixed(4)}</span></div>
          <div class="diff-stat"><span class="label">Delta</span><span class="value ${deltaClass}" style="font-size:15px;font-weight:700;">${deltaStr}</span></div>`;
      } else {
        if (!hasTreatment) html += '<div class="diff-stat"><span class="label">Treatment</span><span class="value" style="color:#ef4444;">No data</span></div>';
        if (!hasBaseline) html += '<div class="diff-stat"><span class="label">Baseline</span><span class="value" style="color:#ef4444;">No data</span></div>';
      }
      html += '</div>';
    });

    // Chart for metrics
    html += '<div class="diff-result-card"><div style="position:relative;height:300px;"><canvas id="diff-chart"></canvas></div></div>';

    // Missing runs
    if (data.missing && data.missing.length > 0) {
      html += '<div class="diff-missing"><div class="diff-missing-title">Missing Runs</div>';
      data.missing.forEach(m => {
        html += `<div class="diff-missing-item">${m.description}</div>`;
      });
      html += '</div>';
    }

    resultsDiv.innerHTML = html;

    // Render diff chart
    const ctx = document.getElementById('diff-chart');
    if (!ctx) return;
    if (diffChart) diffChart.destroy();

    const chartLabels = metricNames;
    const treatmentVals = metricNames.map(m => data.results[m].treatment.mean || 0);
    const baselineVals = metricNames.map(m => data.results[m].baseline.mean || 0);
    const treatmentErrs = metricNames.map(m => data.results[m].treatment.std || 0);
    const baselineErrs = metricNames.map(m => data.results[m].baseline.std || 0);

    const errorBarPlugin = {
      id: 'diffErrorBars',
      afterDatasetsDraw(chart) {
        const { ctx: c, scales: { x, y } } = chart;
        chart.data.datasets.forEach((ds, di) => {
          if (!ds.errorBars) return;
          const meta = chart.getDatasetMeta(di);
          meta.data.forEach((bar, i) => {
            const err = ds.errorBars[i];
            if (!err || err === 0) return;
            const xPos = bar.x;
            const yVal = ds.data[i];
            const yTop = y.getPixelForValue(yVal + err);
            const yBot = y.getPixelForValue(yVal - err);
            const capW = bar.width ? bar.width * 0.3 : 6;
            c.save();
            c.strokeStyle = '#e0e0e0';
            c.lineWidth = 1.5;
            c.beginPath();
            c.moveTo(xPos, yTop);
            c.lineTo(xPos, yBot);
            c.moveTo(xPos - capW, yTop);
            c.lineTo(xPos + capW, yTop);
            c.moveTo(xPos - capW, yBot);
            c.lineTo(xPos + capW, yBot);
            c.stroke();
            c.restore();
          });
        });
      }
    };

    diffChart = new Chart(ctx.getContext('2d'), {
      type: 'bar',
      data: {
        labels: chartLabels,
        datasets: [
          {
            label: `Treatment (${data.treatment_protocol})`,
            data: treatmentVals,
            backgroundColor: '#e94560cc',
            borderColor: '#e94560',
            borderWidth: 1,
            errorBars: treatmentErrs,
          },
          {
            label: `Baseline (${data.baseline_protocol})`,
            data: baselineVals,
            backgroundColor: '#3b82f6cc',
            borderColor: '#3b82f6',
            borderWidth: 1,
            errorBars: baselineErrs,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { labels: { color: '#ccc' } },
          title: { display: true, text: 'Treatment vs Baseline', color: '#e0e0e0' },
        },
        scales: {
          x: { ticks: { color: '#888' }, grid: { color: '#0f3460' } },
          y: { ticks: { color: '#888' }, grid: { color: '#0f3460' }, beginAtZero: true },
        },
      },
      plugins: [errorBarPlugin],
    });
  }

  // Init
  initTerminal();
  loadProtocols();
  refreshState();
  loadTree();
  loadComparisons();
  // Poll faster (2s) to catch auto-advance PTY transitions quickly; tree/comparisons stay at 10s
  setInterval(() => { refreshState(); }, 2000);
  setInterval(() => { loadTree(); loadComparisons(); }, 10000);
</script>
</body>
</html>
"""


def launch_ui(task_dir: str, protocol_name: str = None, host: str = "0.0.0.0",
              port: int = 8765, **kwargs):
    """Store config for deferred init and start the web server."""
    import uvicorn

    state["task_dir"] = task_dir
    state["launch_kwargs"] = {
        k: v for k, v in kwargs.items()
        if k in ("engine_cmd", "model", "run_id", "work_dir", "log_dir")
    }
    state["default_protocol"] = protocol_name

    # If protocol was provided via CLI, initialize immediately
    if protocol_name:
        init_experiment(task_dir, protocol_name, **state["launch_kwargs"])

    print(f"\n  Experiment UI: http://localhost:{port}\n")
    uvicorn.run(app, host=host, port=port, log_level="warning")
