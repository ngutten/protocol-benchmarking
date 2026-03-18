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
from concurrent.futures import ThreadPoolExecutor


app = FastAPI()

# Dedicated thread pool for PTY blocking reads — keeps them from exhausting
# the default asyncio executor (which is small on low-core machines).
_pty_executor = ThreadPoolExecutor(max_workers=24, thread_name_prefix="pty-io")

# ---------------------------------------------------------------------------
# Per-session state
# ---------------------------------------------------------------------------

class RunSession:
    """Holds all state for a single benchmark run session."""

    def __init__(self, session_id: str, task_dir: str = None, task_name: str = None):
        self.session_id = session_id
        self.experiment = None
        self.current_stage_idx = -1
        self.stages: list = []
        self.stage_metrics: list = []
        self.pty_fd = None
        self.child_pid = None
        self.stage_start_time = None
        self.presence_segments: list = []
        self.presence_status = "active"
        self.presence_segment_start = None
        self.paused = False
        self.protocol = None
        self.auto_mode = False
        self.auto_advance = False
        self.auto_status = None       # None, "running", "completing", "advancing"
        self.pty_monitor_task = None   # asyncio.Task for PTY exit monitoring
        self.pty_generation = 0        # incremented each time a new PTY is spawned
        self.task_dir = task_dir
        self.current_task_name = task_name
        self.harness_log: list = []    # circular buffer of harness debug messages
        self.stage_protocols: dict = {}  # stage_id -> protocol_name for per-stage overrides

    def cleanup(self):
        """Clean up PTY resources."""
        if self.pty_monitor_task is not None:
            self.pty_monitor_task.cancel()
            self.pty_monitor_task = None
        if self.child_pid:
            try:
                os.kill(self.child_pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                os.waitpid(self.child_pid, os.WNOHANG)
            except ChildProcessError:
                pass
            self.child_pid = None
        if self.pty_fd is not None:
            try:
                os.close(self.pty_fd)
            except OSError:
                pass
            self.pty_fd = None


# Session registry: session_id -> RunSession
sessions: dict[str, RunSession] = {}

# Global config (from CLI args, not per-session)
_global = {
    "task_dir": None,
    "launch_kwargs": {},
    "default_protocol": None,
    "current_task_name": None,
    "harness_log": [],  # global harness log for non-session events
}

_HARNESS_LOG_MAX = 200


def _get_session(session_id: str) -> RunSession:
    """Look up a session by ID. Returns None if not found."""
    return sessions.get(session_id)


def _remove_session(session_id: str):
    """Remove a session from the registry and clean up global refs."""
    sessions.pop(session_id, None)
    if _global.get("default_session_id") == session_id:
        _global.pop("default_session_id", None)


def _harness_log(msg: str, session: RunSession = None):
    """Append a timestamped message to a harness debug log."""
    ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    entry = f"[{ts}] {msg}"
    log = session.harness_log if session else _global["harness_log"]
    log.append(entry)
    if len(log) > _HARNESS_LOG_MAX:
        del log[:-_HARNESS_LOG_MAX]


def _find_latest_session_id(workspace_path: str) -> str:
    """Find the most recent session JSONL file matching the workspace path.

    Filters by workspace path when possible: Claude encodes project paths
    as directory names using a dash-separated encoding (slashes become dashes).
    We try to match the encoded workspace path to narrow the search.
    """
    claude_dir = Path.home() / ".claude" / "projects"
    if not claude_dir.exists():
        return ""

    # Claude encodes project paths: /home/user/foo/bar -> -home-user-foo-bar
    workspace_abs = str(Path(workspace_path).resolve())
    encoded_path = workspace_abs.replace("/", "-")
    if encoded_path.startswith("-"):
        encoded_path = encoded_path  # keep leading dash

    best_file = None
    best_mtime = 0

    for dirpath, _, filenames in os.walk(claude_dir):
        dir_name = Path(dirpath).name
        # If we can match by encoded workspace path, prefer that
        matches_workspace = encoded_path and encoded_path in dir_name

        for fname in filenames:
            if fname.endswith(".jsonl"):
                fpath = Path(dirpath) / fname
                mtime = fpath.stat().st_mtime
                if matches_workspace and mtime > best_mtime:
                    best_mtime = mtime
                    best_file = fpath

    # Fallback: if no workspace-specific match, use most recent globally
    if not best_file:
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
                    model: str = None, run_id: str = None,
                    stage_protocols: dict = None) -> RunSession:
    """Initialize an experiment and return a RunSession.

    Args:
        stage_protocols: Optional dict mapping stage_id -> protocol_name for
            per-stage protocol assignments. If provided, each stage can use
            a different protocol. The protocol_name arg is used as fallback
            for any stages not in this mapping.
    """
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

    # Apply per-stage protocol overrides.
    # The UI may send un-numbered stage IDs (e.g. "select_where") while the
    # experiment uses numbered IDs (e.g. "01_select_where"). Map both forms.
    if stage_protocols:
        for sid, pname in stage_protocols.items():
            if pname in ALL_PROTOCOLS:
                proto_obj = ALL_PROTOCOLS[pname]
                # Try exact match first
                if sid in exp.stages:
                    exp._stage_protocols[sid] = proto_obj
                else:
                    # Try to find the numbered version
                    for numbered_sid in exp.stages:
                        # numbered_sid is like "01_select_where", sid is "select_where"
                        if numbered_sid.split('_', 1)[-1] == sid or numbered_sid.endswith('_' + sid):
                            exp._stage_protocols[numbered_sid] = proto_obj
                            break

    # Create session
    session = RunSession(
        session_id=exp.run_id,
        task_dir=task_dir,
        task_name=Path(task_dir).name,
    )
    session.experiment = exp
    session.stages = list(exp.stages)
    session.current_stage_idx = -1
    session.stage_metrics = []
    session.protocol = protocol
    session.stage_protocols = stage_protocols or {}

    # Register in global session registry
    sessions[session.session_id] = session

    return session


def _spawn_claude_pty(work_dir: str, prompt: str, protocol, headless: bool = False,
                      session: RunSession = None) -> tuple:
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

    _harness_log(f"spawn: headless={headless} cmd={cmd_parts[0]}...{cmd_parts[1:3]} (prompt {len(prompt)} chars)", session)

    child_pid, master_fd = pty.fork()
    if child_pid == 0:
        os.chdir(work_dir)
        os.execvpe(cmd_parts[0], cmd_parts, env)
    else:
        flag = fcntl.fcntl(master_fd, fcntl.F_GETFL)
        fcntl.fcntl(master_fd, fcntl.F_SETFL, flag | os.O_NONBLOCK)
        return master_fd, child_pid


def _kill_pty(session: RunSession):
    """Kill the PTY process for a session."""
    session.cleanup()


def _compute_human_time(session: RunSession) -> float:
    """Compute total active human time from presence segments."""
    total = 0.0
    for seg in session.presence_segments:
        if seg["status"] == "active":
            end = seg.get("end", time.time())
            total += end - seg["start"]
    return total


def _task_log_dir(task_name: str) -> Path:
    """Return the per-task consolidated log directory (e.g. logs/minidb/)."""
    return Path("logs") / task_name


def _consolidate_log(exp):
    """Copy the experiment log JSON and merge tree nodes into the per-task logs/ subdirectory."""
    if not exp or not exp.log_dir:
        return
    task_name = Path(exp.task_dir).name if exp.task_dir else None
    if task_name:
        consolidated_dir = _task_log_dir(task_name)
    else:
        consolidated_dir = Path("logs")
    consolidated_dir.mkdir(parents=True, exist_ok=True)

    # Copy metrics JSON
    log_file = Path(exp.log_dir) / f"{exp.run_id}.json"
    if log_file.exists():
        shutil.copy2(str(log_file), str(consolidated_dir / log_file.name))

    # Merge run's tree nodes into the consolidated tree, remapping IDs to avoid
    # collisions (each run starts node IDs at node_001).
    run_tree_file = Path(exp.log_dir) / "experiment_tree.json"
    if run_tree_file.exists():
        consolidated_tree = StateTree(str(consolidated_dir))
        with open(run_tree_file) as f:
            run_data = json.load(f)
        run_nodes = run_data.get("nodes", {})
        # Build a mapping from run node IDs to consolidated node IDs.
        # Nodes that already exist (same git_tag) are reused; others get new IDs.
        id_map = {}
        for nid, ndata in run_nodes.items():
            # Check if this exact node already exists by git_tag (unique per commit)
            existing = consolidated_tree.find_by_tag(ndata.get("git_tag", ""))
            if existing:
                id_map[nid] = existing.node_id
            else:
                new_id = consolidated_tree._make_id()
                id_map[nid] = new_id
                node = TreeNode.from_dict(ndata)
                node.node_id = new_id
                # Remap parent reference
                if node.parent and node.parent in id_map:
                    node.parent = id_map[node.parent]
                consolidated_tree.nodes[new_id] = node
        # Second pass: fix parent references for nodes whose parents were mapped
        # after they were inserted
        for nid, ndata in run_nodes.items():
            mapped_id = id_map[nid]
            if mapped_id in consolidated_tree.nodes:
                node = consolidated_tree.nodes[mapped_id]
                if node.parent and node.parent in id_map:
                    node.parent = id_map[node.parent]
        consolidated_tree.save()


def _migrate_legacy_logs():
    """Migrate root-level log files into per-task subdirectories.

    Idempotent: skips if no root-level JSON log files exist.
    """
    logs_dir = Path("logs")
    if not logs_dir.exists():
        return

    # Find root-level JSON files (not in subdirs, not tree file)
    root_jsons = [f for f in logs_dir.glob("*.json") if f.name != "experiment_tree.json"]
    if not root_jsons:
        return

    _harness_log(f"migrate: found {len(root_jsons)} legacy log files")

    # Load root tree if it exists
    root_tree_file = logs_dir / "experiment_tree.json"
    root_tree_data = {}
    if root_tree_file.exists():
        try:
            with open(root_tree_file) as f:
                root_tree_data = json.load(f).get("nodes", {})
        except (json.JSONDecodeError, KeyError):
            pass

    # Map run_id -> task_name from log files
    run_to_task = {}
    for f in root_jsons:
        try:
            with open(f) as fh:
                log = json.load(fh)
            task_path = log.get("task", "")
            if not task_path:
                continue
            task_name = Path(task_path).name
            run_id = log.get("run_id", f.stem)
            run_to_task[run_id] = task_name

            # Move log file to per-task dir
            dest_dir = _task_log_dir(task_name)
            dest_dir.mkdir(parents=True, exist_ok=True)
            dest = dest_dir / f.name
            if not dest.exists():
                shutil.move(str(f), str(dest))
                _harness_log(f"migrate: {f.name} -> {dest_dir.name}/")
            else:
                f.unlink()
        except (json.JSONDecodeError, KeyError):
            continue

    # Distribute tree nodes into per-task trees based on run_id
    if root_tree_data:
        task_nodes = {}  # task_name -> {nid: ndata}
        for nid, ndata in root_tree_data.items():
            # Match node's run_id to a task
            node_run_id = ndata.get("run_id", "")
            task_name = run_to_task.get(node_run_id)
            if not task_name:
                # Try to match by checking if run_id prefix matches any known task
                for rid, tname in run_to_task.items():
                    if node_run_id and node_run_id == rid:
                        task_name = tname
                        break
            if task_name:
                task_nodes.setdefault(task_name, {})[nid] = ndata

        for task_name, nodes in task_nodes.items():
            task_dir = _task_log_dir(task_name)
            task_dir.mkdir(parents=True, exist_ok=True)
            tree = StateTree(str(task_dir))
            for nid, ndata in nodes.items():
                if nid not in tree.nodes:
                    tree.nodes[nid] = TreeNode.from_dict(ndata)
            if tree.nodes:
                max_num = max(
                    int(nid.split("_")[1]) for nid in tree.nodes
                    if nid.startswith("node_") and nid.split("_")[1].isdigit()
                )
                tree._next_id = max(tree._next_id, max_num + 1)
            tree.save()

        # Remove root tree after successful migration
        try:
            root_tree_file.unlink()
            _harness_log("migrate: removed root experiment_tree.json")
        except OSError:
            pass

    _harness_log("migrate: legacy log migration complete")


async def _monitor_pty_exit(session: RunSession):
    """Background task that monitors the child PID for exit.

    When the process exits (claude -p finishes), auto-completes the stage
    and optionally auto-advances to the next stage.
    """
    child_pid = session.child_pid
    if not child_pid:
        _harness_log("monitor: no child_pid, exiting", session)
        return

    _harness_log(f"monitor: watching PID {child_pid}", session)

    try:
        while True:
            try:
                pid, exit_status = os.waitpid(child_pid, os.WNOHANG)
                if pid != 0:
                    _harness_log(f"monitor: PID {child_pid} exited (status={exit_status})", session)
                    break
            except ChildProcessError:
                _harness_log(f"monitor: PID {child_pid} already reaped", session)
                exit_status = 0
                break
            await asyncio.sleep(0.25)
    except asyncio.CancelledError:
        _harness_log("monitor: cancelled", session)
        return

    # Brief delay for final PTY output to flush
    await asyncio.sleep(0.5)

    # Auto-complete the stage (check it hasn't been manually completed already)
    if session.current_stage_idx < 0:
        _harness_log("monitor: stage already completed (manual or race), skipping auto-complete", session)
        return

    await _auto_complete_stage(session)

    # Auto-advance if enabled
    if session.auto_advance:
        await _auto_start_next_stage(session)


async def _auto_complete_stage(session: RunSession):
    """Programmatically complete the current stage (same logic as POST /api/stage/complete)."""
    exp = session.experiment
    if exp is None or session.current_stage_idx < 0:
        _harness_log(f"auto_complete: skipped (exp={exp is not None}, idx={session.current_stage_idx})", session)
        return

    stage_id = session.stages[session.current_stage_idx]
    _harness_log(f"auto_complete: starting for stage {stage_id} (idx={session.current_stage_idx})", session)
    session.auto_status = "completing"

    # Close presence segment
    if session.presence_segments:
        session.presence_segments[-1]["end"] = time.time()

    human_time = _compute_human_time(session)
    wall_time = time.time() - session.stage_start_time if session.stage_start_time else human_time

    # Don't kill PTY here — process already exited, just clean up fd
    # Clear the child_pid since the process already exited (waitpid was done in monitor)
    session.child_pid = None
    session.pty_monitor_task = None
    if session.pty_fd is not None:
        try:
            os.close(session.pty_fd)
        except OSError:
            pass
        session.pty_fd = None

    # Run blocking I/O in executor to avoid stalling the event loop
    loop = asyncio.get_event_loop()

    # Find claude session ID from recent JSONL files
    claude_session_id = await loop.run_in_executor(
        _pty_executor, _find_latest_session_id, str(exp.work_dir))

    # Get token usage
    token_data = None
    if claude_session_id:
        usage = await loop.run_in_executor(
            _pty_executor, get_session_token_usage, claude_session_id)
        if usage["total_tokens"] > 0:
            token_data = usage

    # Complete stage via experiment (runs tests — can be slow)
    _harness_log(f"auto_complete: running metrics for {stage_id} (claude_session={claude_session_id}, tokens={token_data.get('total_tokens', 0) if token_data else 0})", session)
    try:
        metrics = await loop.run_in_executor(
            _pty_executor,
            lambda: exp.complete_stage(stage_id, human_time=human_time, wall_time=wall_time, token_data=token_data))
        metrics_dict = metrics.to_dict()
    except Exception as e:
        _harness_log(f"auto_complete: ERROR in complete_stage: {e}", session)
        session.auto_status = None
        session.current_stage_idx = -1
        return

    session.stage_metrics.append(metrics_dict)
    session.current_stage_idx = -1
    session.auto_status = None
    _harness_log(f"auto_complete: done for {stage_id} (train={metrics_dict.get('training_tests_passed')}/{metrics_dict.get('training_tests_total')})", session)

    # Auto-save log and consolidate
    await loop.run_in_executor(_pty_executor, exp.save_log)
    await loop.run_in_executor(_pty_executor, _consolidate_log, exp)


async def _auto_start_next_stage(session: RunSession):
    """Programmatically start the next stage after a brief delay."""
    exp = session.experiment
    if not exp:
        _harness_log("auto_advance: no experiment", session)
        return

    next_idx = len(session.stage_metrics)
    if next_idx >= len(session.stages):
        _harness_log("auto_advance: all stages complete", session)
        session.auto_status = None
        return

    _harness_log(f"auto_advance: waiting 2s before stage {next_idx}", session)
    session.auto_status = "advancing"
    await asyncio.sleep(2)

    # Re-check in case user aborted during the delay
    if not session.auto_mode or session.experiment is None:
        _harness_log("auto_advance: aborted during delay", session)
        session.auto_status = None
        return

    next_idx = len(session.stage_metrics)
    if next_idx >= len(session.stages):
        _harness_log("auto_advance: all stages complete (after delay)", session)
        session.auto_status = None
        return

    stage_id = session.stages[next_idx]
    _harness_log(f"auto_advance: starting stage {stage_id} (idx={next_idx})", session)
    session.current_stage_idx = next_idx

    exp.prepare_stage(stage_id)
    prompt = exp.build_stage_prompt(stage_id)

    # Start presence tracking (away in semi-auto mode)
    session.presence_segments = []
    session.presence_status = "away"
    session.presence_segment_start = time.time()
    session.presence_segments.append({
        "start": time.time(), "status": "away"
    })
    session.stage_start_time = time.time()

    # Spawn claude in PTY with headless mode (use per-stage protocol)
    _kill_pty(session)
    stage_protocol = exp.get_protocol_for_stage(stage_id)
    master_fd, child_pid = _spawn_claude_pty(
        str(exp.work_dir), prompt, stage_protocol, headless=True, session=session
    )
    session.pty_fd = master_fd
    session.child_pid = child_pid
    session.pty_generation += 1
    session.auto_status = "running"

    # Start monitoring for this new stage
    session.pty_monitor_task = asyncio.create_task(_monitor_pty_exit(session))


# ---- API Routes ----

@app.get("/")
async def index():
    return HTMLResponse(DASHBOARD_HTML)


@app.get("/api/sessions")
async def list_sessions():
    """List all active sessions."""
    result = []
    for sid, s in sessions.items():
        completed = len([m for m in s.stage_metrics if isinstance(m, dict) and not m.get("skipped")])
        result.append({
            "session_id": sid,
            "task_name": s.current_task_name,
            "task_dir": s.task_dir,
            "protocol": s.protocol.name if s.protocol else None,
            "stages_completed": completed,
            "stages_total": len(s.stages),
            "pty_active": s.child_pid is not None,
            "auto_mode": s.auto_mode,
        })
    return {"sessions": result}


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
        "default": _global["default_protocol"],
    }


from fastapi import Request as FastAPIRequest


@app.post("/api/task/select")
async def select_task(request: FastAPIRequest):
    """Select (or switch) the active task directory for the requesting tab.

    Only cleans up a session if the tab's own session_id is provided.
    Does NOT modify global state — each tab tracks its own task selection.
    """
    body = await request.json()
    task_dir = body.get("task_dir")
    old_session_id = body.get("session_id")
    if not task_dir or not Path(task_dir).is_dir():
        return {"error": f"Invalid task directory: {task_dir}"}

    # If an existing session was provided, clean it up
    if old_session_id and old_session_id in sessions:
        old_session = sessions[old_session_id]
        exp = old_session.experiment
        if exp:
            try:
                exp.save_log()
                _consolidate_log(exp)
            except Exception:
                pass
        _kill_pty(old_session)
        _remove_session(old_session_id)

    task_name = Path(task_dir).name

    # Load task config
    cfg = load_task_config(task_dir)
    stages = [s["id"] if isinstance(s, dict) else s for s in cfg.get("stages", [])]
    pipelines = cfg.get("pipelines", {})

    # Load existing tree for this task
    tree_dir = _task_log_dir(task_name)
    tree_data = {}
    if tree_dir.exists():
        tree = StateTree(str(tree_dir))
        tree_data = tree.to_dict().get("nodes", {})

    return {
        "task_name": cfg.get("name", task_name),
        "task_dir": task_dir,
        "stages": stages,
        "pipelines": pipelines,
        "tree_nodes": tree_data,
    }


@app.post("/api/experiment/init")
async def init_experiment_api(request: FastAPIRequest):
    """Initialize (or re-initialize) experiment with per-stage protocol assignments.

    Returns session_id which must be used in all subsequent API calls.
    """
    body = await request.json()
    protocol_name = body.get("protocol")
    stage_protocols = body.get("stage_protocols", {})
    old_session_id = body.get("session_id")

    if not protocol_name or protocol_name not in ALL_PROTOCOLS:
        return {"error": f"Invalid protocol: {protocol_name}"}

    # Validate all per-stage protocol names
    for sid, pname in stage_protocols.items():
        if pname not in ALL_PROTOCOLS:
            return {"error": f"Invalid protocol for stage {sid}: {pname}"}

    task_dir = body.get("task_dir") or _global["task_dir"]
    if not task_dir:
        return {"error": "No task directory configured"}

    # Clean up old session if re-initializing
    if old_session_id and old_session_id in sessions:
        old_session = sessions[old_session_id]
        _kill_pty(old_session)
        _remove_session(old_session_id)

    # Initialize with stored kwargs
    kwargs = dict(_global["launch_kwargs"])
    kwargs["model"] = kwargs.pop("model", None)
    session = init_experiment(task_dir, protocol_name, stage_protocols=stage_protocols, **kwargs)

    exp = session.experiment
    return {
        "session_id": session.session_id,
        "run_id": exp.run_id,
        "stages": list(exp.stages),
        "protocol": protocol_name,
        "stage_protocols": stage_protocols,
    }


@app.post("/api/auto/configure")
async def configure_auto(request: FastAPIRequest):
    """Enable or disable semi-auto mode."""
    body = await request.json()
    session_id = body.get("session_id")
    session = _get_session(session_id) if session_id else None
    if not session:
        return {"error": "Invalid session_id"}
    session.auto_mode = bool(body.get("auto_mode", False))
    session.auto_advance = bool(body.get("auto_advance", session.auto_mode))
    return {
        "auto_mode": session.auto_mode,
        "auto_advance": session.auto_advance,
    }


@app.get("/api/state")
async def get_state(session_id: str = None):
    # If no session_id, try the default session (from CLI init).
    # Consume it so only the first browser tab picks it up.
    if not session_id and _global.get("default_session_id"):
        session_id = _global.pop("default_session_id")
    # NOTE: We intentionally do NOT auto-select a session when there's only
    # one active.  That caused a second browser tab to silently adopt (and
    # then destroy) the first tab's session during init.
    if not session_id:
        return {
            "initialized": False,
            "stages": [],
            "current_stage_idx": -1,
            "protocol": None,
            "model": None,
            "paused": False,
            "presence_status": "active",
            "pty_active": False,
            "live_stats": None,
            "cumulative_tokens": 0,
            "cumulative_human_time": 0,
            "auto_mode": False,
            "auto_advance": False,
            "auto_status": None,
            "harness_log": _global["harness_log"][-20:],
            "task_dir": _global["task_dir"],
            "current_task_name": _global["current_task_name"],
            "stage_protocols": {},
            "session_id": None,
        }

    session = _get_session(session_id)
    if not session:
        return {"error": f"Session not found: {session_id}", "initialized": False}

    exp = session.experiment
    stages_info = []
    for i, sid in enumerate(session.stages):
        info = {"id": sid, "status": "pending"}
        if i < len(session.stage_metrics):
            info["status"] = "completed"
            info["metrics"] = session.stage_metrics[i]
        elif i == session.current_stage_idx:
            info["status"] = "in_progress"
        stages_info.append(info)

    # Compute live stats
    live_stats = None
    if session.current_stage_idx >= 0 and session.stage_start_time:
        wall_elapsed = time.time() - session.stage_start_time
        human_time = _compute_human_time(session)
        # Try to get live token count (run in executor to avoid blocking event loop)
        live_tokens = 0
        if exp:
            loop = asyncio.get_event_loop()
            claude_session_id = await loop.run_in_executor(
                _pty_executor, _find_latest_session_id, str(exp.work_dir))
            if claude_session_id:
                try:
                    usage = await loop.run_in_executor(
                        _pty_executor, get_session_token_usage, claude_session_id)
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
        m.get("total_tokens", 0) for m in session.stage_metrics
        if isinstance(m, dict) and not m.get("skipped")
    )
    cumulative_human_time = sum(
        m.get("human_time_seconds", 0) for m in session.stage_metrics
        if isinstance(m, dict) and not m.get("skipped")
    )

    return {
        "initialized": exp is not None,
        "session_id": session.session_id,
        "stages": stages_info,
        "current_stage_idx": session.current_stage_idx,
        "protocol": session.protocol.name if session.protocol else None,
        "model": session.protocol.model if session.protocol else None,
        "paused": session.paused,
        "presence_status": session.presence_status,
        "pty_active": session.child_pid is not None,
        "live_stats": live_stats,
        "cumulative_tokens": cumulative_tokens,
        "cumulative_human_time": round(cumulative_human_time, 1),
        "auto_mode": session.auto_mode,
        "auto_advance": session.auto_advance,
        "auto_status": session.auto_status,
        "harness_log": session.harness_log[-20:],
        "task_dir": session.task_dir,
        "current_task_name": session.current_task_name,
        "stage_protocols": session.stage_protocols,
    }


@app.get("/api/harness-log")
async def get_harness_log(session_id: str = None):
    """Return the full harness debug log."""
    if session_id:
        session = _get_session(session_id)
        if session:
            return {"log": session.harness_log}
    return {"log": _global["harness_log"]}


@app.post("/api/stage/start")
async def start_stage(request: FastAPIRequest):
    body = await request.json()
    session_id = body.get("session_id")
    session = _get_session(session_id) if session_id else None
    if not session:
        return {"error": "Invalid session_id"}
    exp = session.experiment
    if not exp:
        return {"error": "No experiment initialized"}

    next_idx = len(session.stage_metrics)
    if next_idx >= len(session.stages):
        return {"error": "All stages completed"}

    stage_id = session.stages[next_idx]
    _harness_log(f"start_stage: {stage_id} (idx={next_idx}, auto={session.auto_mode})", session)
    session.current_stage_idx = next_idx

    exp.prepare_stage(stage_id)
    prompt = exp.build_stage_prompt(stage_id)

    # Start presence tracking (away by default in semi-auto mode)
    initial_presence = "away" if session.auto_mode else "active"
    session.presence_segments = []
    session.presence_status = initial_presence
    session.presence_segment_start = time.time()
    session.presence_segments.append({
        "start": time.time(), "status": initial_presence
    })
    session.stage_start_time = time.time()

    # Spawn claude in PTY (use per-stage protocol if available)
    _kill_pty(session)
    headless = session.auto_mode
    stage_protocol = exp.get_protocol_for_stage(stage_id)
    master_fd, child_pid = _spawn_claude_pty(
        str(exp.work_dir), prompt, stage_protocol, headless=headless, session=session
    )
    session.pty_fd = master_fd
    session.child_pid = child_pid
    session.pty_generation += 1

    # In auto mode, start monitoring for process exit
    if headless:
        session.auto_status = "running"
        session.pty_monitor_task = asyncio.create_task(_monitor_pty_exit(session))

    return {"session_id": session.session_id, "stage_id": stage_id, "stage_idx": next_idx, "prompt": prompt}


@app.post("/api/stage/complete")
async def complete_stage(request: FastAPIRequest):
    body = await request.json()
    session_id = body.get("session_id")
    session = _get_session(session_id) if session_id else None
    if not session:
        return {"error": "Invalid session_id"}
    exp = session.experiment
    if exp is None or session.current_stage_idx < 0:
        _harness_log(f"complete_stage: rejected (exp={exp is not None}, idx={session.current_stage_idx}, auto_status={session.auto_status})", session)
        return {"error": "No stage in progress"}

    stage_id = session.stages[session.current_stage_idx]
    _harness_log(f"complete_stage: manual complete for {stage_id}", session)

    # Close presence segment
    if session.presence_segments:
        session.presence_segments[-1]["end"] = time.time()

    human_time = _compute_human_time(session)
    wall_time = time.time() - session.stage_start_time if session.stage_start_time else human_time

    # Kill PTY
    _kill_pty(session)

    # Run blocking I/O in executor to avoid stalling the event loop
    loop = asyncio.get_event_loop()

    # Find claude session ID from recent JSONL files
    claude_session_id = await loop.run_in_executor(
        _pty_executor, _find_latest_session_id, str(exp.work_dir))

    # Get token usage
    token_data = None
    if claude_session_id:
        usage = await loop.run_in_executor(
            _pty_executor, get_session_token_usage, claude_session_id)
        if usage["total_tokens"] > 0:
            token_data = usage

    # Complete stage via experiment (runs tests — can be slow)
    metrics = await loop.run_in_executor(
        _pty_executor,
        lambda: exp.complete_stage(stage_id, human_time=human_time, wall_time=wall_time, token_data=token_data))
    metrics_dict = metrics.to_dict()

    session.stage_metrics.append(metrics_dict)
    session.current_stage_idx = -1

    # Auto-save log and consolidate
    await loop.run_in_executor(_pty_executor, exp.save_log)
    await loop.run_in_executor(_pty_executor, _consolidate_log, exp)

    return {"stage_id": stage_id, "metrics": metrics_dict}


@app.post("/api/stage/skip")
async def skip_stage(request: FastAPIRequest):
    body = await request.json()
    session_id = body.get("session_id")
    session = _get_session(session_id) if session_id else None
    if not session:
        return {"error": "Invalid session_id"}
    exp = session.experiment
    if not exp:
        return {"error": "No experiment initialized"}

    next_idx = session.current_stage_idx if session.current_stage_idx >= 0 else len(session.stage_metrics)
    if next_idx >= len(session.stages):
        return {"error": "All stages completed"}

    _kill_pty(session)
    stage_id = session.stages[next_idx]
    session.stage_metrics.append({"stage_id": stage_id, "skipped": True})
    session.current_stage_idx = -1
    exp.completed_stages.append(stage_id)
    return {"stage_id": stage_id, "skipped": True}


@app.post("/api/presence/toggle")
async def toggle_presence(request: FastAPIRequest):
    body = await request.json()
    session_id = body.get("session_id")
    session = _get_session(session_id) if session_id else None
    if not session:
        return {"error": "Invalid session_id"}
    now = time.time()
    if session.presence_segments:
        session.presence_segments[-1]["end"] = now

    new_status = "away" if session.presence_status == "active" else "active"
    session.presence_status = new_status
    session.presence_segments.append({"start": now, "status": new_status})
    return {"status": new_status}


@app.post("/api/experiment/abort")
async def abort_experiment(request: FastAPIRequest):
    body = await request.json()
    session_id = body.get("session_id")
    session = _get_session(session_id) if session_id else None
    if not session:
        return {"error": "Invalid session_id"}
    _kill_pty(session)
    exp = session.experiment
    if exp:
        exp.save_log()
        _consolidate_log(exp)
    # Remove from registry
    _remove_session(session_id)
    return {"aborted": True}


@app.get("/api/tree")
async def get_tree(task: str = None):
    """Return the experiment state tree, optionally per-task."""
    task_name = task or _global.get("current_task_name")
    if task_name:
        log_dir = _task_log_dir(task_name)
    else:
        log_dir = Path("logs")
    if not log_dir.exists():
        return {"nodes": {}}
    tree = StateTree(str(log_dir))
    return tree.to_dict()


@app.get("/api/pipelines")
async def get_pipelines():
    """Return available pipelines for the current task."""
    task_dir = _global.get("task_dir")
    if not task_dir:
        return {"pipelines": {}}
    cfg = load_task_config(task_dir)
    return {"pipelines": cfg.get("pipelines", {})}


@app.get("/api/comparisons/available")
async def get_available_comparisons(task: str = None):
    """Return computable and missing differential comparisons."""
    task_name = task or _global.get("current_task_name")
    if task_name:
        log_dir = _task_log_dir(task_name)
    else:
        log_dir = Path("logs")
    if not log_dir.exists():
        return {"available": [], "missing": []}
    tree = StateTree(str(log_dir))
    available = tree.list_available_comparisons()

    # Determine what's missing based on task pipelines
    task_dir = _global.get("task_dir")
    missing = []
    if task_dir:
        cfg = load_task_config(task_dir)
        all_stages = [s["id"] for s in cfg.get("stages", [])]
        all_protocols = sorted(ALL_PROTOCOLS.keys())
        missing = tree.list_missing_comparisons(all_stages, all_protocols)

    return {"available": available, "missing": missing}


@app.post("/api/experiment/fork")
async def fork_experiment(request: FastAPIRequest):
    """Initialize a new experiment forked from an existing tree node.

    Returns a new session_id for the forked experiment.
    """
    body = await request.json()
    node_id = body.get("node_id")
    protocol_name = body.get("protocol")
    pipeline_name = body.get("pipeline")
    slots = body.get("slots", {})
    old_session_id = body.get("session_id")

    if not node_id:
        return {"error": "node_id is required"}
    if not protocol_name or protocol_name not in ALL_PROTOCOLS:
        return {"error": f"Invalid protocol: {protocol_name}"}

    task_dir = body.get("task_dir") or _global["task_dir"]
    if not task_dir:
        return {"error": "No task directory configured"}

    # Clean up old session if provided
    if old_session_id and old_session_id in sessions:
        _kill_pty(sessions[old_session_id])
        _remove_session(old_session_id)

    protocol = ALL_PROTOCOLS[protocol_name]
    kwargs = dict(_global["launch_kwargs"])
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
        engine_cmd=kwargs.get("engine_cmd", ""),
        pipeline_name=pipeline_name,
        slots=slots,
    )
    exp.setup(fork_from_node=node_id)

    session = RunSession(
        session_id=exp.run_id,
        task_dir=task_dir,
        task_name=Path(task_dir).name,
    )
    session.experiment = exp
    session.stages = exp.get_pipeline_stages_list() if pipeline_name else list(exp.stages)
    session.current_stage_idx = -1
    session.stage_metrics = []
    session.protocol = protocol
    session.presence_segments = []
    session.presence_status = "active"

    # Mark forked stages as completed in metrics list
    for sid in exp.completed_stages:
        session.stage_metrics.append({"stage_id": sid, "skipped": True, "forked": True})

    # Register session
    sessions[session.session_id] = session

    return {
        "session_id": session.session_id,
        "run_id": exp.run_id,
        "stages": session.stages,
        "protocol": protocol_name,
        "forked_from": node_id,
        "completed_stages": list(exp.completed_stages),
    }


@app.websocket("/ws/terminal/{session_id}")
async def terminal_ws(ws: WebSocket, session_id: str):
    """WebSocket bridge between xterm.js and the PTY for a specific session.

    Reads from session.pty_fd dynamically so it survives stage transitions.
    When a PTY closes (process exit), waits briefly for a new PTY to appear
    (e.g. from auto-advance) instead of immediately disconnecting.
    """
    await ws.accept()

    session = _get_session(session_id)
    if not session or session.pty_fd is None:
        await ws.send_text("\r\nNo terminal session active. Click 'Start Stage' first.\r\n")
        await ws.close()
        return

    async def _notify_stage_transition(new_gen):
        """Send a stage transition banner to the terminal."""
        try:
            stage_idx = session.current_stage_idx
            if stage_idx >= 0 and stage_idx < len(session.stages):
                stage_id = session.stages[stage_idx]
                await ws.send_text(f"\r\n\x1b[1;36m--- Starting stage: {stage_id} ---\x1b[0m\r\n\r\n")
        except (WebSocketDisconnect, OSError):
            pass

    async def read_pty():
        """Read from PTY and send to WebSocket, following fd changes across stages."""
        loop = asyncio.get_event_loop()
        current_fd = session.pty_fd
        current_gen = session.pty_generation
        try:
            while True:
                # Check if a new PTY generation appeared
                if session.pty_generation > current_gen and session.pty_fd is not None:
                    current_fd = session.pty_fd
                    current_gen = session.pty_generation
                    await _notify_stage_transition(current_gen)

                if current_fd is None or session.pty_fd is None:
                    # PTY closed — wait for a new one (auto-advance) or give up
                    new_fd, new_gen = await _wait_for_new_pty(session, current_gen)
                    if new_fd is None:
                        await ws.send_text("\r\n[Process exited]\r\n")
                        break
                    current_fd = new_fd
                    current_gen = new_gen
                    await _notify_stage_transition(current_gen)
                    continue

                try:
                    data = await loop.run_in_executor(_pty_executor, _blocking_read_pty, current_fd)
                    if data is None:
                        # EOF — fd is dead. Wait for a replacement.
                        new_fd, new_gen = await _wait_for_new_pty(session, current_gen)
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
                if payload and session.pty_fd is not None:
                    os.write(session.pty_fd, payload)
            except (WebSocketDisconnect, OSError):
                break

    try:
        await asyncio.gather(read_pty(), write_pty())
    except Exception:
        pass


async def _wait_for_new_pty(session: RunSession, old_gen: int, timeout: float = 60.0):
    """Wait up to `timeout` seconds for a new PTY generation to appear.

    Returns (new_fd, new_gen) or (None, old_gen) if no new PTY appeared.
    Timeout is generous because metrics collection between stages can be slow.
    """
    if not session.auto_mode:
        return None, old_gen
    _harness_log(f"ws: waiting for new PTY (gen={old_gen}, timeout={timeout}s)", session)
    deadline = time.time() + timeout
    while time.time() < deadline:
        await asyncio.sleep(0.3)
        if session.pty_generation > old_gen and session.pty_fd is not None:
            _harness_log(f"ws: PTY gen {old_gen} -> {session.pty_generation} (fd={session.pty_fd})", session)
            return session.pty_fd, session.pty_generation
    _harness_log(f"ws: no new PTY after {timeout}s (gen={old_gen})", session)
    return None, old_gen


@app.websocket("/ws/resize/{session_id}")
async def resize_ws(ws: WebSocket, session_id: str):
    """Receive terminal resize events for a specific session."""
    await ws.accept()
    session = _get_session(session_id)
    while True:
        try:
            data = await ws.receive_json()
            if session and session.pty_fd is not None:
                winsize = struct.pack("HHHH", data["rows"], data["cols"], 0, 0)
                fcntl.ioctl(session.pty_fd, termios.TIOCSWINSZ, winsize)
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


def _is_total_failure(log):
    """A run is a total failure if any stage had tests to pass but passed zero.

    Checks each stage independently — a run that passes stage 1 but completely
    fails stage 2 (zero tests passed) is still a total failure.
    """
    for s in log.get("stages", []):
        if s.get("skipped"):
            continue
        stage_tests = s.get("training_tests_total", 0) + s.get("holdout_tests_total", 0)
        stage_passed = s.get("training_tests_passed", 0) + s.get("holdout_tests_passed", 0)
        if stage_tests > 0 and stage_passed == 0:
            return True
    return False


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
            # Flag runs that passed zero tests as total failures
            log["total_failure"] = _is_total_failure(log)
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
def get_logs():
    """Return all experiment logs with metrics (stripped of test_results)."""
    return {"runs": _load_all_logs()}


@app.get("/api/tasks")
def get_tasks():
    """Return all task configurations with stage metadata."""
    return {"tasks": _load_all_tasks()}


@app.post("/api/differential/analyze")
async def analyze_differential(request: FastAPIRequest):
    """Compute A/B differential analysis — all non-baseline protocols vs baseline.

    Body: {
        task: "tasks/minidb",
        group_a: [0, 1],         # stage indices for group A
        group_b: [2],            # stage indices for group B
        baseline: "direct_tests_provided",
        metrics: ["holdout_accuracy", "effective_tokens"]
    }

    For each non-baseline protocol found in data, computes:
      Treatment condition: that protocol on A stages, baseline on B stages.
      Baseline condition: baseline protocol on all A and B stages.
    """
    body = await request.json()
    task_path = body.get("task", "")
    group_a = body.get("group_a", [])
    group_b = body.get("group_b", [])
    baseline_proto = body.get("baseline", "")
    metric_names = body.get("metrics", ["holdout_accuracy"])

    # Load task config and logs in executor to avoid blocking the event loop
    loop = asyncio.get_event_loop()
    tasks = await loop.run_in_executor(_pty_executor, _load_all_tasks)
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
    logs = await loop.run_in_executor(_pty_executor, _load_all_logs)
    task_logs = [l for l in logs
                 if l.get("task", "").rstrip("/").endswith(task_path.split("/")[-1])
                 and not l.get("total_failure")]

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

    # Snapshot metrics record cumulative totals (e.g. total code size), not
    # per-stage deltas.  For the differential we need the change during B, so
    # we subtract the value at the end of the last A stage.
    SNAPSHOT_METRICS = {"code_lines", "code_bytes"}

    def _get_b_value(metric, stage_data, stages_data, a_stages_set):
        """Return the metric value for a B stage, adjusting snapshots to deltas."""
        val = stage_data.get(metric)
        if val is None:
            return None
        if metric not in SNAPSHOT_METRICS:
            return val
        # Find the last A stage (by position in the run) to use as baseline
        a_vals = []
        for s in stages_data:
            sid = s.get("stage_id", "")
            if sid in a_stages_set or any(sid.endswith(f"_{a}") for a in a_stages_set):
                v = s.get(metric)
                if v is not None:
                    a_vals.append(v)
        if a_vals:
            return val - a_vals[-1]  # delta = B snapshot - last A snapshot
        return val  # no A stage found, return raw (shouldn't happen)

    # Discover all non-baseline protocols used on A stages across logs
    all_protocols = set()
    for log in task_logs:
        for sid in a_stages:
            p = get_stage_protocol(log, sid)
            if p:
                all_protocols.add(p)
    all_protocols.discard(baseline_proto)
    treatment_protocols = sorted(all_protocols)

    if not treatment_protocols:
        return {"error": f"No non-baseline protocols found in data (baseline={baseline_proto})"}

    # Find matching runs.
    # For each treatment protocol T:
    #   Treatment condition: T on A stages, baseline on B stages (M(A_t, B_b)).
    # Baseline condition: baseline on all A+B stages (M(A_b, B_b)).
    per_treatment_metric_values = {tp: {m: [] for m in metric_names} for tp in treatment_protocols}
    per_treatment_runs = {tp: [] for tp in treatment_protocols}
    found_treatments = {tp: False for tp in treatment_protocols}
    baseline_metric_values = {m: [] for m in metric_names}
    baseline_runs = []
    found_baseline = False

    for log in task_logs:
        stages_data = log.get("stages", [])
        proto_map = {}
        for sid in list(a_stages) + list(b_stages):
            proto_map[sid] = get_stage_protocol(log, sid)

        # Baseline: baseline on all stages
        all_baseline = all(proto_map.get(s) == baseline_proto for s in a_stages | b_stages)
        if all_baseline:
            found_baseline = True
            baseline_runs.append({
                "run_id": log.get("run_id", "unknown"),
                "protocol_map": dict(proto_map),
            })
            for sid in b_stages:
                stage_data = match_stage_id(sid, stages_data)
                if stage_data:
                    for m in metric_names:
                        val = _get_b_value(m, stage_data, stages_data, a_stages)
                        if val is not None:
                            baseline_metric_values[m].append(val)

        # Check each treatment protocol
        b_baseline = all(proto_map.get(s) == baseline_proto for s in b_stages)
        if b_baseline:
            for tp in treatment_protocols:
                a_treatment = all(proto_map.get(s) == tp for s in a_stages)
                if a_treatment:
                    found_treatments[tp] = True
                    per_treatment_runs[tp].append({
                        "run_id": log.get("run_id", "unknown"),
                        "protocol_map": dict(proto_map),
                    })
                    for sid in b_stages:
                        stage_data = match_stage_id(sid, stages_data)
                        if stage_data:
                            for m in metric_names:
                                val = _get_b_value(m, stage_data, stages_data, a_stages)
                                if val is not None:
                                    per_treatment_metric_values[tp][m].append(val)

    # Compute stats
    def compute_stats(values):
        if not values:
            return {"n": 0, "values": [], "mean": None, "std": None, "se": None}
        mean = sum(values) / len(values)
        if len(values) > 1:
            variance = sum((v - mean) ** 2 for v in values) / (len(values) - 1)
            std = math.sqrt(variance)
        else:
            std = 0.0
        se = std / math.sqrt(len(values)) if len(values) >= 1 else 0.0
        return {"n": len(values), "values": values, "mean": mean, "std": std, "se": se}

    results = {}
    for m in metric_names:
        baseline_stats = compute_stats(baseline_metric_values[m])
        treatments = {}
        for tp in treatment_protocols:
            t_stats = compute_stats(per_treatment_metric_values[tp][m])
            delta = None
            if t_stats["mean"] is not None and baseline_stats["mean"] is not None:
                delta = t_stats["mean"] - baseline_stats["mean"]
            treatments[tp] = {"stats": t_stats, "delta": delta}
        results[m] = {"baseline": baseline_stats, "treatments": treatments}

    # Determine missing runs
    missing = []
    a_list = sorted(a_stages)
    b_list = sorted(b_stages)
    for tp in treatment_protocols:
        if not found_treatments[tp]:
            missing.append({
                "condition": "treatment",
                "protocol": tp,
                "description": (
                    f"Need a run with {tp} on A stages [{', '.join(a_list)}] "
                    f"and {baseline_proto} on B stages [{', '.join(b_list)}]."
                ),
                "protocol_map": {s: tp for s in a_list} | {s: baseline_proto for s in b_list},
                "fork_hint": {
                    "explanation": f"Run pipeline with A={tp}, B={baseline_proto}",
                    "a_stages": a_list,
                    "b_stages": b_list,
                    "a_protocol": tp,
                    "b_protocol": baseline_proto,
                },
            })
    if not found_baseline:
        missing.append({
            "condition": "baseline",
            "description": f"Need a run with {baseline_proto} on all stages [{', '.join(sorted(a_stages | b_stages))}]",
            "protocol_map": {s: baseline_proto for s in sorted(a_stages | b_stages)},
            "fork_hint": {
                "explanation": f"Run pipeline with {baseline_proto} on all stages",
                "a_stages": a_list,
                "b_stages": b_list,
                "a_protocol": baseline_proto,
                "b_protocol": baseline_proto,
            },
        })

    return {
        "results": results,
        "missing": missing,
        "treatment_runs": per_treatment_runs,
        "baseline_runs": baseline_runs,
        "group_a": a_list,
        "group_b": b_list,
        "treatment_protocols": treatment_protocols,
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
  #tree-overlay svg text { user-select: none; }
  #tree-overlay svg g:hover rect { filter: brightness(1.3); }
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
  .pareto-axis-config { border: 1px solid #0f3460; border-radius: 6px; padding: 10px; margin-bottom: 10px; }
  .pareto-axis-title { font-size: 12px; font-weight: 600; color: #e94560; margin-bottom: 6px; }
  .stage-proto-row { display: flex; align-items: center; gap: 6px; margin-bottom: 4px; }
  .stage-proto-row .stage-label { font-size: 12px; color: #ccc; min-width: 90px; flex-shrink: 0; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .stage-proto-row select { flex: 1; padding: 3px 4px; font-size: 11px; border-radius: 4px; border: 1px solid #0f3460; background: #1a1a2e; color: #e0e0e0; }
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
  <button class="tab-btn" onclick="switchTab('pareto')">Pareto Analysis</button>
</div>
<!-- Tab: Experiment (default) -->
<div id="tab-experiment" class="tab-content active" style="flex-direction:column;flex:1;">
<div class="main" style="flex:1;">
  <div class="sidebar-left">
    <div class="section-title">Task</div>
    <select id="task-select" onchange="selectTask()">
      <option value="">Select a task...</option>
    </select>
    <div class="proto-desc" id="task-desc"></div>
    <div class="section-title">Set All Protocols</div>
    <div style="display:flex;gap:4px;margin-bottom:8px;">
      <select id="protocol-select-all" style="flex:1;" onchange="setAllProtocols()">
        <option value="">Loading...</option>
      </select>
    </div>
    <div class="proto-desc" id="proto-desc"></div>
    <div class="section-title">Stages &amp; Protocols</div>
    <div id="stage-protocol-list" style="margin-bottom:8px;"></div>
    <button class="btn-primary btn-init" id="btn-init" onclick="initExperiment()">Initialize Experiment</button>
    <div class="section-title">Run Progress</div>
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
        <option value="failed_run_pct">Failed Run % (zero tests passed)</option>
        <option value="wall_time_seconds">Wall Time (s)</option>
        <option value="human_time_seconds">Human Time (s)</option>
        <option value="output_tokens">Output Tokens</option>
        <option value="effective_tokens">Effective Tokens</option>
        <option value="total_tokens">Total Tokens</option>
        <option value="code_lines">Code Lines</option>
        <option value="input_tokens">Input Tokens</option>
        <option value="cache_creation_tokens">Cache Write Tokens</option>
        <option value="cache_read_tokens">Cache Read Tokens</option>
        <option value="perf_mean_duration">Perf Mean Duration (s)</option>
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
      <div class="viz-checkbox-row">
        <input type="checkbox" id="viz-normalize">
        <label for="viz-normalize">Normalize within stages</label>
      </div>
      <div style="font-size:10px;color:#666;margin-left:20px;">
        Cumulative only: divide by cross-protocol stage mean before averaging. Accuracies become error rates.
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
        <div class="viz-checkbox-row"><input type="checkbox" value="perf_mean_duration"><label>Perf Mean Duration (s)</label></div>
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
          Group A = stages where treatment protocols are applied.<br>
          Group B = stages where the baseline protocol is applied (measurement point).<br><br>
          All non-baseline protocols found in data are compared against the baseline.<br>
          Treatment: non-baseline protocol on A, baseline on B<br>
          vs. Baseline: baseline on all of A+B<br><br>
          The effect is measured on the B stages.
        </div>
      </div>
    </div>
  </div>
</div>

<!-- Tab: Pareto Analysis -->
<div id="tab-pareto" class="tab-content">
  <div class="viz-container">
    <div class="viz-sidebar" style="width:360px;">
      <div class="viz-label">Task Filter</div>
      <select class="viz-select" id="pareto-task" onchange="paretoTaskChanged()">
        <option value="">All Tasks</option>
      </select>

      <div class="viz-label">Stage / Tag Filter</div>
      <select class="viz-select" id="pareto-stage-filter">
        <option value="">All stages</option>
      </select>

      <div class="pareto-axis-config">
        <div class="pareto-axis-title">X Axis</div>
        <select class="viz-select" id="pareto-x-metric">
          <option value="effective_tokens">Effective Tokens</option>
          <option value="holdout_accuracy">Holdout Accuracy</option>
          <option value="training_accuracy">Training Accuracy</option>
          <option value="regression_rate">Regression Rate</option>
          <option value="failed_run_pct">Failed Run %</option>
          <option value="wall_time_seconds">Wall Time (s)</option>
          <option value="human_time_seconds">Human Time (s)</option>
          <option value="output_tokens">Output Tokens</option>
          <option value="total_tokens">Total Tokens</option>
          <option value="code_lines">Code Lines</option>
          <option value="perf_mean_duration">Perf Mean Duration (s)</option>
        </select>
        <div class="viz-label">Mode</div>
        <select class="viz-select" id="pareto-x-mode" onchange="paretoModeChanged()">
          <option value="raw">Raw (per-protocol mean)</option>
          <option value="differential">Sequential Differential (Δ)</option>
        </select>
        <div class="viz-label">Direction</div>
        <select class="viz-select" id="pareto-x-dir">
          <option value="lower">Lower is better</option>
          <option value="higher">Higher is better</option>
        </select>
      </div>

      <div class="pareto-axis-config">
        <div class="pareto-axis-title">Y Axis</div>
        <select class="viz-select" id="pareto-y-metric">
          <option value="holdout_accuracy" selected>Holdout Accuracy</option>
          <option value="training_accuracy">Training Accuracy</option>
          <option value="regression_rate">Regression Rate</option>
          <option value="failed_run_pct">Failed Run %</option>
          <option value="effective_tokens">Effective Tokens</option>
          <option value="wall_time_seconds">Wall Time (s)</option>
          <option value="human_time_seconds">Human Time (s)</option>
          <option value="output_tokens">Output Tokens</option>
          <option value="total_tokens">Total Tokens</option>
          <option value="code_lines">Code Lines</option>
          <option value="perf_mean_duration">Perf Mean Duration (s)</option>
        </select>
        <div class="viz-label">Mode</div>
        <select class="viz-select" id="pareto-y-mode" onchange="paretoModeChanged()">
          <option value="raw">Raw (per-protocol mean)</option>
          <option value="differential">Sequential Differential (Δ)</option>
        </select>
        <div class="viz-label">Direction</div>
        <select class="viz-select" id="pareto-y-dir">
          <option value="higher">Higher is better</option>
          <option value="lower">Lower is better</option>
        </select>
      </div>

      <div id="pareto-diff-config" style="display:none;">
        <div class="viz-label">Baseline Protocol</div>
        <select class="viz-select" id="pareto-baseline"></select>
        <div class="viz-label">Treatment Stages (A)</div>
        <div class="diff-preset-bar" id="pareto-presets"></div>
        <div id="pareto-stage-selector"></div>
        <div style="font-size:11px;color:#666;margin-top:4px;">
          A = treatment stages, B = measurement stages.<br>
          Δ = M(T on A, baseline on B) − M(baseline on all)
        </div>
      </div>

      <button class="viz-btn" onclick="renderParetoChart()">Update Chart</button>
      <div class="viz-info" id="pareto-info">Configure axes and click Update Chart.</div>
    </div>
    <div class="viz-main">
      <div class="viz-chart-wrap">
        <canvas id="pareto-chart"></canvas>
      </div>
    </div>
  </div>
</div>

<!-- Fork dialog -->
<div id="fork-dialog" style="display:none; position:fixed; top:50%; left:50%; transform:translate(-50%,-50%); background:#16213e; border:1px solid #0f3460; border-radius:10px; padding:20px; z-index:1001; min-width:380px;">
  <h3 style="margin-bottom:12px; color:#e94560;">Fork from Existing State</h3>
  <div id="fork-node-info" style="display:none;margin-bottom:10px;padding:8px;background:#1a1a2e;border-radius:6px;font-size:12px;color:#aaa;"></div>
  <label style="font-size:13px;color:#888;">Node ID:</label>
  <input id="fork-node-id" style="width:100%;padding:6px;border-radius:6px;border:1px solid #0f3460;background:#1a1a2e;color:#e0e0e0;margin-bottom:8px;" placeholder="e.g. node_001">
  <div style="font-size:11px;color:#666;margin-bottom:8px;">Fork starts AFTER this node's completion.</div>
  <label style="font-size:13px;color:#888;">Protocol:</label>
  <select id="fork-protocol" style="width:100%;padding:6px;border-radius:6px;border:1px solid #0f3460;background:#1a1a2e;color:#e0e0e0;margin-bottom:8px;"></select>
  <label style="font-size:13px;color:#888;">Pipeline (optional):</label>
  <select id="fork-pipeline" style="width:100%;padding:6px;border-radius:6px;border:1px solid #0f3460;background:#1a1a2e;color:#e0e0e0;margin-bottom:12px;">
    <option value="">None</option>
  </select>
  <div style="display:flex;gap:8px;">
    <button class="btn-primary" onclick="executeFork()">Fork</button>
    <button class="btn-secondary" onclick="document.getElementById('fork-dialog').style.display='none';selectedForkNode=null;">Cancel</button>
  </div>
</div>
<div id="fork-dialog-backdrop" style="display:none;position:fixed;inset:0;background:rgba(0,0,0,0.5);z-index:1000;" onclick="document.getElementById('fork-dialog').style.display='none';this.style.display='none';selectedForkNode=null;"></div>

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
  let currentTaskName = null;
  let tasksData = {};
  let currentTaskStages = [];  // stage IDs for the selected task
  let currentSessionId = null; // session ID for the active experiment

  // Visualization state
  let vizChart = null;
  let vizLogsData = null;
  let vizTasksData = null;
  let diffChart = []; // array of per-metric charts
  let paretoChart = null;

  function switchTab(tabId) {
    document.querySelectorAll('.tab-content').forEach(el => el.classList.remove('active'));
    document.querySelectorAll('.tab-btn').forEach(el => el.classList.remove('active'));
    const tab = document.getElementById('tab-' + tabId);
    if (tab) tab.classList.add('active');
    // Activate the button
    const buttons = document.querySelectorAll('.tab-btn');
    const tabNames = ['experiment', 'visualizer', 'differential', 'pareto'];
    const idx = tabNames.indexOf(tabId);
    if (idx >= 0 && buttons[idx]) buttons[idx].classList.add('active');
    // Resize terminal when switching back to experiment tab
    if (tabId === 'experiment' && fitAddon) {
      setTimeout(() => fitAddon.fit(), 50);
    }
    // Load viz data when switching to visualizer or differential
    if (tabId === 'visualizer' || tabId === 'differential' || tabId === 'pareto') {
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

  async function loadTasks() {
    try {
      const res = await fetch('/api/tasks');
      const data = await res.json();
      tasksData = data.tasks || {};
      const select = document.getElementById('task-select');
      select.innerHTML = '<option value="">Select a task...</option>';
      Object.entries(tasksData).forEach(([path, cfg]) => {
        const opt = document.createElement('option');
        opt.value = path;
        opt.textContent = cfg.name || path.split('/').pop();
        select.appendChild(opt);
      });
      // Pre-select if task was set via CLI
      const stateRes = await fetch('/api/state' + (currentSessionId ? '?session_id=' + encodeURIComponent(currentSessionId) : ''));
      const stateData = await stateRes.json();
      // Pick up session_id from server if initialized via CLI
      if (stateData.session_id && !currentSessionId) {
        currentSessionId = stateData.session_id;
      }
      if (stateData.task_dir) {
        select.value = stateData.task_dir;
        currentTaskName = stateData.current_task_name || null;
        document.getElementById('task-desc').textContent =
          tasksData[stateData.task_dir]?.name || '';
        // Load stage list for pre-selected task
        const cfg = tasksData[stateData.task_dir];
        if (cfg && cfg.stages) {
          currentTaskStages = cfg.stages.map(s => typeof s === 'object' ? s.id : s);
        }
        buildStageProtocolList();
      }
      updateInitButton();
    } catch(e) {
      console.error('Failed to load tasks:', e);
    }
  }

  async function selectTask() {
    const taskDir = document.getElementById('task-select').value;
    if (!taskDir) {
      currentTaskName = null;
      currentTaskStages = [];
      document.getElementById('task-desc').textContent = '';
      document.getElementById('stage-list').innerHTML = '';
      document.getElementById('stage-protocol-list').innerHTML = '';
      updateInitButton();
      return;
    }
    try {
      const res = await fetch('/api/task/select', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({task_dir: taskDir, session_id: currentSessionId}),
      });
      currentSessionId = null; // reset session on task switch
      const data = await res.json();
      if (data.error) {
        term.writeln('Error selecting task: ' + data.error);
        return;
      }
      currentTaskName = data.task_name;
      currentTaskStages = data.stages || [];
      document.getElementById('task-desc').textContent = data.task_name;
      term.clear();
      term.writeln(`Switched to task: ${data.task_name}`);
      term.writeln(`Stages: ${data.stages.join(', ')}`);
      term.writeln('Assign protocols to stages and click "Initialize Experiment" to begin.\\r\\n');
      buildStageProtocolList();
      refreshState();
      loadTree();
      loadComparisons();
      updateInitButton();
    } catch(e) {
      term.writeln('Error: ' + e.message);
    }
  }

  function updateInitButton() {
    const taskSelected = !!document.getElementById('task-select').value;
    // Check that all stages have a protocol assigned
    const allAssigned = currentTaskStages.length > 0 && currentTaskStages.every(sid => {
      const sel = document.getElementById('stage-proto-' + sid);
      return sel && sel.value;
    });
    document.getElementById('btn-init').disabled = !(taskSelected && allAssigned);
    // Warn if experiment already initialized (e.g. after fork)
    const btn = document.getElementById('btn-init');
    if (btn._experimentActive) {
      btn.textContent = 'Re-Initialize (resets fork)';
    } else {
      btn.textContent = 'Initialize Experiment';
    }
  }

  async function loadProtocols() {
    const res = await fetch('/api/protocols');
    const data = await res.json();
    protocolsData = data.protocols;
    const select = document.getElementById('protocol-select-all');
    select.innerHTML = '<option value="">(select to set all)</option>';
    protocolsData.forEach(p => {
      const opt = document.createElement('option');
      opt.value = p.name;
      opt.textContent = p.name;
      select.appendChild(opt);
    });
    // Pre-select default if provided
    if (data.default && protocolsData.some(p => p.name === data.default)) {
      select.value = data.default;
      setAllProtocols();
    }
    updateProtocolInfo();
    updateInitButton();
  }

  function buildStageProtocolList() {
    const container = document.getElementById('stage-protocol-list');
    container.innerHTML = '';
    if (currentTaskStages.length === 0) {
      container.innerHTML = '<div style="color:#555;font-size:12px;font-style:italic;">Select a task to see stages</div>';
      return;
    }
    const defaultProto = document.getElementById('protocol-select-all').value;
    currentTaskStages.forEach(sid => {
      const row = document.createElement('div');
      row.className = 'stage-proto-row';
      const label = document.createElement('span');
      label.className = 'stage-label';
      label.textContent = sid.replace(/_/g, ' ');
      label.title = sid;
      row.appendChild(label);
      const sel = document.createElement('select');
      sel.id = 'stage-proto-' + sid;
      sel.onchange = () => { updateInitButton(); };
      protocolsData.forEach(p => {
        const opt = document.createElement('option');
        opt.value = p.name;
        opt.textContent = p.name;
        sel.appendChild(opt);
      });
      if (defaultProto) sel.value = defaultProto;
      row.appendChild(sel);
      container.appendChild(row);
    });
    updateInitButton();
  }

  function setAllProtocols() {
    const proto = document.getElementById('protocol-select-all').value;
    if (!proto) return;
    currentTaskStages.forEach(sid => {
      const sel = document.getElementById('stage-proto-' + sid);
      if (sel) sel.value = proto;
    });
    updateProtocolInfo();
    updateInitButton();
  }

  function updateProtocolInfo() {
    // Show info for the "set all" protocol if selected, else show nothing
    const name = document.getElementById('protocol-select-all').value;
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
    const taskDir = document.getElementById('task-select').value;
    if (!taskDir) { term.writeln('Please select a task first.'); return; }

    // Collect per-stage protocol assignments
    const stageProtocols = {};
    let firstProtocol = null;
    for (const sid of currentTaskStages) {
      const sel = document.getElementById('stage-proto-' + sid);
      if (!sel || !sel.value) { term.writeln(`Please assign a protocol to stage: ${sid}`); return; }
      stageProtocols[sid] = sel.value;
      if (!firstProtocol) firstProtocol = sel.value;
    }
    if (!firstProtocol) { term.writeln('No stages to initialize.'); return; }

    // Warn if an experiment (possibly forked) is already active
    const btn = document.getElementById('btn-init');
    if (btn._experimentActive) {
      if (!confirm('An experiment is already initialized (possibly from a fork). Re-initializing will start fresh from stage 1. Continue?')) return;
    }
    btn.disabled = true;
    btn.textContent = 'Initializing...';
    term.clear();

    // Summarize protocol assignments
    const uniqueProtos = [...new Set(Object.values(stageProtocols))];
    if (uniqueProtos.length === 1) {
      term.writeln(`Initializing experiment with protocol: ${uniqueProtos[0]}...\\r\\n`);
    } else {
      term.writeln('Initializing experiment with per-stage protocols:');
      for (const [sid, proto] of Object.entries(stageProtocols)) {
        term.writeln(`  ${sid}: ${proto}`);
      }
      term.writeln('');
    }

    const res = await fetch('/api/experiment/init', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({protocol: firstProtocol, stage_protocols: stageProtocols, session_id: currentSessionId, task_dir: document.getElementById('task-select').value}),
    });
    const data = await res.json();
    document.getElementById('btn-init').disabled = false;
    document.getElementById('btn-init').textContent = 'Initialize Experiment';
    if (data.error) {
      term.writeln('Error: ' + data.error);
      return;
    }
    currentSessionId = data.session_id;
    term.writeln(`Run ID: ${data.run_id} (session: ${data.session_id})`);
    term.writeln(`Stages: ${data.stages.join(', ')}\\r\\n`);
    term.writeln('Click "Start Stage" to begin.\\r\\n');
    refreshState();
  }

  function connectTerminal() {
    if (termWs) { try { termWs.close(); } catch(e) {} }
    const proto = location.protocol === 'https:' ? 'wss' : 'ws';
    termWs = new WebSocket(`${proto}://${location.host}/ws/terminal/${currentSessionId}`);
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
    resizeWs = new WebSocket(`${proto}://${location.host}/ws/resize/${currentSessionId}`);
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
      const url = '/api/state' + (currentSessionId ? '?session_id=' + encodeURIComponent(currentSessionId) : '');
      const res = await fetch(url);
      const data = await res.json();
      // Pick up session_id from server (e.g. CLI-initialized)
      if (data.session_id && !currentSessionId) {
        currentSessionId = data.session_id;
      }

      // If session was deleted server-side, reset so we stop polling a dead session
      if (data.error && currentSessionId) {
        currentSessionId = null;
        return;
      }

      // Header info
      if (data.initialized) {
        const stageProtos = data.stage_protocols || {};
        const uniqueProtos = [...new Set(Object.values(stageProtos))];
        let protoLabel = data.protocol || '?';
        if (uniqueProtos.length > 1) {
          protoLabel = uniqueProtos.length + ' protocols (mixed)';
        } else if (uniqueProtos.length === 1) {
          protoLabel = uniqueProtos[0];
        }
        document.getElementById('header-info').textContent =
          `Protocol: ${protoLabel} | Model: ${data.model || '?'}`;
      }

      // Stage list (run progress)
      const list = document.getElementById('stage-list');
      list.innerHTML = '';
      const stageProtos = data.stage_protocols || {};
      (data.stages || []).forEach((s) => {
        const div = document.createElement('div');
        div.className = 'stage-item ' + s.status;
        let label = s.id.replace(/_/g, ' ');
        // Show protocol assignment for this stage
        const stageProto = stageProtos[s.id] || stageProtos[s.id.split('_').slice(1).join('_')] || data.protocol;
        const protoBadge = stageProto ? `<span style="font-size:10px;color:#888;margin-left:4px;">[${stageProto}]</span>` : '';
        div.innerHTML = `<div>${label}${protoBadge}</div>`;
        if (s.metrics && !s.metrics.skipped) {
          let perfBit = (s.metrics.perf_tests_total > 0)
            ? ` | Perf: ${s.metrics.perf_tests_passed}/${s.metrics.perf_tests_total}`
            : '';
          div.innerHTML += `<div class="metrics-mini">
            Train: ${s.metrics.training_tests_passed}/${s.metrics.training_tests_total}
            | Holdout: ${s.metrics.holdout_tests_passed}/${s.metrics.holdout_tests_total}${perfBit}
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
      const stages = data.stages || [];
      const allDone = stages.length > 0 && stages.every(s => s.status === 'completed' || s.metrics?.skipped);
      document.getElementById('btn-start').disabled = !data.initialized || hasActive || allDone;
      document.getElementById('btn-init')._experimentActive = data.initialized;
      updateInitButton();
      document.getElementById('btn-complete').disabled = !hasActive;
      document.getElementById('btn-skip').disabled = !data.initialized || allDone;

      const btn = document.getElementById('btn-presence');
      btn.textContent = data.presence_status === 'active' ? 'Active' : 'Away';
      btn.className = data.presence_status === 'active' ? 'presence-active' : 'presence-away';

      // Live stats
      const completed = stages.filter(s => s.status === 'completed').length;
      const total = stages.length;
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
        const stageId = stages[data.current_stage_idx]?.id || '?';
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
    const res = await fetch('/api/stage/start', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({session_id: currentSessionId})});
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
    const res = await fetch('/api/stage/complete', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({session_id: currentSessionId})});
    const data = await res.json();
    if (data.error) { term.writeln('Error: ' + data.error); return; }
    const m = data.metrics;
    term.writeln(`\\r\\n--- Stage ${data.stage_id} Complete ---`);
    term.writeln(`Training: ${m.training_tests_passed}/${m.training_tests_total}`);
    term.writeln(`Holdout: ${m.holdout_tests_passed}/${m.holdout_tests_total}`);
    if (m.perf_tests_total > 0) {
      term.writeln(`Perf: ${m.perf_tests_passed}/${m.perf_tests_total} benchmarks (avg ${(m.perf_mean_duration||0).toFixed(4)}s)`);
    }
    term.writeln(`Tokens: ${(m.total_tokens||0).toLocaleString()}`);
    term.writeln(`Code: ${m.code_lines} lines\\r\\n`);
    refreshState();
  }

  async function skipStage() {
    const res = await fetch('/api/stage/skip', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({session_id: currentSessionId})});
    await res.json();
    refreshState();
  }

  async function togglePresence() {
    const res = await fetch('/api/presence/toggle', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({session_id: currentSessionId})});
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
      body: JSON.stringify({auto_mode: newMode, auto_advance: newMode, session_id: currentSessionId}),
    });
    const data = await res.json();
    btn.classList.toggle('active', data.auto_mode);
    btn.textContent = data.auto_mode ? 'Semi-Auto: ON' : 'Semi-Auto';
    refreshState();
  }

  async function abortExperiment() {
    if (!confirm('Abort the experiment? Progress will be saved.')) return;
    await fetch('/api/experiment/abort', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({session_id: currentSessionId})});
    term.writeln('\\r\\nExperiment aborted. Log saved.');
    currentSessionId = null;
    refreshState();
  }

  let treeNodesData = {};
  let selectedForkNode = null;

  async function loadTree() {
    try {
      const taskParam = currentTaskName ? `?task=${encodeURIComponent(currentTaskName)}` : '';
      const res = await fetch('/api/tree' + taskParam);
      const data = await res.json();
      const panel = document.getElementById('panel-tree');
      const nodes = data.nodes || {};
      treeNodesData = nodes;
      const ids = Object.keys(nodes).sort();
      if (ids.length === 0) {
        panel.textContent = 'No experiment history yet.';
        panel.className = 'info-panel empty';
        return;
      }
      // Collect unique protocols for legend
      const protos = [...new Set(ids.map(id => nodes[id].protocol))].sort();
      protos.forEach(p => getProtocolColor(p)); // assign colors

      let html = `<div style="margin-bottom:6px;font-size:11px;color:#888;">${ids.length} node${ids.length !== 1 ? 's' : ''}</div>`;
      // Protocol legend
      html += '<div style="margin-bottom:8px;">';
      protos.forEach(p => {
        html += `<span style="display:inline-block;margin-right:8px;"><span style="display:inline-block;width:8px;height:8px;border-radius:2px;background:${getProtocolColor(p)};margin-right:3px;"></span><span style="font-size:10px;color:#aaa;">${p}</span></span>`;
      });
      html += '</div>';
      html += `<button class="btn-secondary" style="width:100%;font-size:11px;padding:4px 8px;" onclick="showTreeOverlay()">Expand Tree</button>`;
      panel.innerHTML = html;
      panel.className = 'info-panel';
    } catch(e) {}
  }

  function showTreeOverlay() {
    // Remove existing overlay
    let overlay = document.getElementById('tree-overlay');
    if (overlay) overlay.remove();

    const nodes = treeNodesData;
    const ids = Object.keys(nodes).sort();
    if (ids.length === 0) return;

    // Build adjacency: children map + roots
    const children = {};
    const roots = [];
    ids.forEach(id => { children[id] = []; });
    ids.forEach(id => {
      const parent = nodes[id].parent;
      if (parent && children[parent]) {
        children[parent].push(id);
      } else {
        roots.push(id);
      }
    });

    // Layout: assign (col, row) positions via DFS
    const NODE_W = 110, NODE_H = 36, GAP_X = 20, GAP_Y = 12;
    const positions = {};
    let nextRow = 0;

    function layoutNode(id, col) {
      const kids = children[id] || [];
      if (kids.length === 0) {
        positions[id] = { col, row: nextRow };
        nextRow++;
      } else {
        kids.forEach((kid, ki) => {
          layoutNode(kid, col + 1);
        });
        // Parent row = average of children rows
        const childRows = kids.map(k => positions[k].row);
        const avgRow = childRows.reduce((a, b) => a + b, 0) / childRows.length;
        positions[id] = { col, row: avgRow };
      }
    }
    roots.forEach(r => layoutNode(r, 0));

    // Compute SVG dimensions
    const maxCol = Math.max(...Object.values(positions).map(p => p.col));
    const maxRow = Math.max(...Object.values(positions).map(p => p.row));
    const svgW = (maxCol + 1) * (NODE_W + GAP_X) + GAP_X;
    const svgH = (maxRow + 1) * (NODE_H + GAP_Y) + GAP_Y;

    function nodeX(col) { return GAP_X + col * (NODE_W + GAP_X); }
    function nodeY(row) { return GAP_Y + row * (NODE_H + GAP_Y); }

    // Build SVG
    let svg = `<svg width="${svgW}" height="${svgH}" xmlns="http://www.w3.org/2000/svg" style="font-family:system-ui,sans-serif;">`;

    // Edges (bezier curves)
    ids.forEach(id => {
      (children[id] || []).forEach(kid => {
        const p = positions[id];
        const c = positions[kid];
        const x1 = nodeX(p.col) + NODE_W;
        const y1 = nodeY(p.row) + NODE_H / 2;
        const x2 = nodeX(c.col);
        const y2 = nodeY(c.row) + NODE_H / 2;
        const cx = (x1 + x2) / 2;
        svg += `<path d="M${x1},${y1} C${cx},${y1} ${cx},${y2} ${x2},${y2}" fill="none" stroke="#0f3460" stroke-width="2"/>`;
      });
    });

    // Nodes
    ids.forEach(id => {
      const n = nodes[id];
      const p = positions[id];
      const x = nodeX(p.col);
      const y = nodeY(p.row);
      const color = getProtocolColor(n.protocol);
      const isSelected = selectedForkNode === id;
      const strokeW = isSelected ? 3 : 1.5;
      const fillOpacity = isSelected ? 0.3 : 0.1;
      const truncStage = n.stage_id.length > 12 ? n.stage_id.slice(0, 11) + '…' : n.stage_id;
      const protoAbbr = n.protocol.length > 10 ? n.protocol.slice(0, 9) + '…' : n.protocol;

      svg += `<g style="cursor:pointer;" onclick="selectTreeNode('${id}')">`;
      svg += `<rect x="${x}" y="${y}" width="${NODE_W}" height="${NODE_H}" rx="6" ry="6" fill="${color}" fill-opacity="${fillOpacity}" stroke="${color}" stroke-width="${strokeW}"/>`;
      svg += `<text x="${x + NODE_W/2}" y="${y + 14}" text-anchor="middle" fill="#e0e0e0" font-size="10" style="user-select:none;">${truncStage}</text>`;
      svg += `<text x="${x + NODE_W/2}" y="${y + 27}" text-anchor="middle" fill="${color}" font-size="9" style="user-select:none;">${protoAbbr}</text>`;
      svg += '</g>';
    });
    svg += '</svg>';

    // Create overlay
    overlay = document.createElement('div');
    overlay.id = 'tree-overlay';
    overlay.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,0.8);z-index:1000;display:flex;flex-direction:column;align-items:center;';
    overlay.innerHTML = `
      <div style="display:flex;justify-content:space-between;align-items:center;width:100%;padding:16px 24px;">
        <span style="color:#e0e0e0;font-size:14px;font-weight:600;">Experiment Tree</span>
        <button onclick="document.getElementById('tree-overlay').remove()" style="background:none;border:1px solid #555;color:#e0e0e0;padding:4px 12px;border-radius:6px;cursor:pointer;">Close</button>
      </div>
      <div style="flex:1;overflow:auto;padding:0 24px 24px;">${svg}</div>
    `;
    document.body.appendChild(overlay);
  }

  function selectTreeNode(nodeId) {
    selectedForkNode = nodeId;
    // Re-render tree overlay with selection highlight
    showTreeOverlay();
    // Pre-fill fork dialog
    const nodeInput = document.getElementById('fork-node-id');
    if (nodeInput) nodeInput.value = nodeId;
    // Close overlay and open fork dialog
    const overlay = document.getElementById('tree-overlay');
    if (overlay) overlay.remove();
    showForkDialog();
    // Set the node ID after dialog opens
    setTimeout(() => {
      const inp = document.getElementById('fork-node-id');
      if (inp) inp.value = nodeId;
    }, 50);
  }

  async function loadComparisons() {
    try {
      const taskParam = currentTaskName ? `?task=${encodeURIComponent(currentTaskName)}` : '';
      const res = await fetch('/api/comparisons/available' + taskParam);
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
    const backdrop = document.getElementById('fork-dialog-backdrop');
    // Show node info if a node is selected
    const infoDiv = document.getElementById('fork-node-info');
    if (selectedForkNode && treeNodesData[selectedForkNode]) {
      const n = treeNodesData[selectedForkNode];
      infoDiv.innerHTML = `<span style="color:${getProtocolColor(n.protocol)};">&#9632;</span> <strong>${selectedForkNode}</strong> — stage: ${n.stage_id}, protocol: ${n.protocol}, run: ${n.run_id}`;
      infoDiv.style.display = 'block';
      document.getElementById('fork-node-id').value = selectedForkNode;
    } else {
      infoDiv.style.display = 'none';
    }
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
    if (backdrop) backdrop.style.display = 'block';
    dialog.style.display = 'block';
  }

  async function executeFork() {
    const nodeId = document.getElementById('fork-node-id').value.trim();
    const protocol = document.getElementById('fork-protocol').value;
    const pipeline = document.getElementById('fork-pipeline').value;
    if (!nodeId) { alert('Enter a node ID'); return; }
    document.getElementById('fork-dialog').style.display = 'none';
    const backdrop = document.getElementById('fork-dialog-backdrop');
    if (backdrop) backdrop.style.display = 'none';
    selectedForkNode = null;
    term.clear();
    term.writeln(`Forking from ${nodeId} with protocol ${protocol}...\\r\\n`);
    const body = {node_id: nodeId, protocol: protocol, session_id: currentSessionId};
    if (pipeline) body.pipeline = pipeline;
    const res = await fetch('/api/experiment/fork', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(body),
    });
    const data = await res.json();
    if (data.error) { term.writeln('Error: ' + data.error); return; }
    currentSessionId = data.session_id;
    term.writeln(`Forked! Run ID: ${data.run_id} (session: ${data.session_id})`);
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

  // Protocol color mapping for consistent colors across tree and viz
  const protocolColorMap = {};
  function getProtocolColor(proto) {
    if (protocolColorMap[proto]) return protocolColorMap[proto];
    const idx = Object.keys(protocolColorMap).length;
    protocolColorMap[proto] = VIZ_COLORS[idx % VIZ_COLORS.length];
    return protocolColorMap[proto];
  }

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
      populateParetoSelectors();
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
    const normalize = document.getElementById('viz-normalize').checked;
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

    // Count total failures before filtering
    const allRuns = runs;
    const failedRunCounts = {}; // protocol -> {failed, total}
    allRuns.forEach(r => {
      const p = r.protocol;
      if (!failedRunCounts[p]) failedRunCounts[p] = { failed: 0, total: 0 };
      failedRunCounts[p].total++;
      if (r.total_failure) failedRunCounts[p].failed++;
    });
    const totalFailedRuns = allRuns.filter(r => r.total_failure).length;

    // Handle failed_run_pct as a special cumulative-only metric
    const isFailedRunMetric = metric === 'failed_run_pct';

    // Filter out total failures from normal metrics
    if (!isFailedRunMetric) {
      runs = runs.filter(r => !r.total_failure);
    }

    // Collect all protocols and stages
    // Include per-stage protocols (from stage_protocols map and stage-level fields)
    const protocolSet = new Set();
    allRuns.forEach(r => {
      protocolSet.add(r.protocol);
      const sp = r.stage_protocols || {};
      Object.values(sp).forEach(p => protocolSet.add(p));
      (r.stages || []).forEach(s => { if (s.protocol) protocolSet.add(s.protocol); });
    });
    const protocols = [...protocolSet].sort();
    let stageIds = [];
    runs.forEach(r => {
      (r.stages || []).forEach(s => {
        if (!stageIds.includes(s.stage_id)) stageIds.push(s.stage_id);
      });
    });

    // Build data index: {protocol -> {stage_id -> [values]}}
    // Use per-stage protocol field (not run-level) so mixed-protocol runs
    // attribute each stage's data to the correct protocol.
    const dataIndex = {};
    protocols.forEach(p => { dataIndex[p] = {}; });
    runs.forEach(r => {
      const sp = r.stage_protocols || {};
      (r.stages || []).forEach(s => {
        const val = s[metric];
        if (val == null) return;
        // Per-stage protocol: check stage_protocols map, then stage-level field, then run-level
        const proto = sp[s.stage_id] || s.protocol || r.protocol;
        if (!dataIndex[proto]) dataIndex[proto] = {};
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

    // Compute mean, std (sample standard deviation), and se (standard error) for each cell
    function stats(arr) {
      if (!arr || arr.length === 0) return { mean: 0, std: 0, se: 0, n: 0 };
      const mean = arr.reduce((a, b) => a + b, 0) / arr.length;
      if (arr.length < 2) return { mean, std: 0, se: 0, n: arr.length };
      const variance = arr.reduce((a, b) => a + (b - mean) ** 2, 0) / (arr.length - 1);
      const std = Math.sqrt(variance);
      return { mean, std, se: std / Math.sqrt(arr.length), n: arr.length };
    }

    let labels, datasets;

    if (isFailedRunMetric) {
      // Special metric: failed run percentage per protocol (always cumulative)
      labels = protocols;
      const values = protocols.map(p => {
        const c = failedRunCounts[p] || { failed: 0, total: 0 };
        return c.total > 0 ? c.failed / c.total : 0;
      });
      datasets = [{
        label: 'Failed Run %',
        data: values,
        backgroundColor: VIZ_COLORS.slice(0, protocols.length),
        borderColor: VIZ_COLORS.slice(0, protocols.length),
        borderWidth: 1,
        rawValues: protocols.map(p => {
          // Each run is a 0 or 1 observation
          const c = failedRunCounts[p] || { failed: 0, total: 0 };
          const obs = [];
          for (let i = 0; i < c.failed; i++) obs.push(1);
          for (let i = 0; i < c.total - c.failed; i++) obs.push(0);
          return obs;
        }),
      }];
    } else if (viewMode === 'cumulative') {
      // Cumulative: one bar per protocol, aggregated across stages.
      // When normalize is on, values are expressed relative to the cross-protocol
      // stage mean so that stages with different scales can be meaningfully averaged.
      // For accuracy metrics, we convert to error rate (1 - accuracy) first.
      labels = protocols;
      const isRate = ['holdout_accuracy', 'training_accuracy', 'regression_rate'].includes(metric);
      const isAccuracy = ['holdout_accuracy', 'training_accuracy'].includes(metric);
      const values = [];
      const errors = [];

      // Step 1: Compute per-protocol per-stage means
      const protoStageMeans = {}; // {proto -> {stage -> mean}}
      protocols.forEach(p => {
        protoStageMeans[p] = {};
        stageIds.forEach(sid => {
          const vals = dataIndex[p]?.[sid] || [];
          if (vals.length > 0) {
            let mean = vals.reduce((a, b) => a + b, 0) / vals.length;
            if (normalize && isAccuracy) mean = 1 - mean; // convert to error rate
            protoStageMeans[p][sid] = mean;
          }
        });
      });

      // Step 2: Compute per-stage grand means (average of per-protocol means)
      const grandMeans = {};
      stageIds.forEach(sid => {
        const protoMeans = [];
        protocols.forEach(p => {
          if (protoStageMeans[p][sid] != null) protoMeans.push(protoStageMeans[p][sid]);
        });
        grandMeans[sid] = protoMeans.length > 0
          ? protoMeans.reduce((a, b) => a + b, 0) / protoMeans.length
          : 0;
      });

      protocols.forEach(p => {
        if (isRate || normalize) {
          // Bar height: mean of (optionally normalized) per-stage means
          const stageMeans = [];
          stageIds.forEach(sid => {
            let vals = dataIndex[p]?.[sid] || [];
            if (vals.length === 0) return;
            let mean = vals.reduce((a, b) => a + b, 0) / vals.length;
            if (normalize && isAccuracy) mean = 1 - mean; // error rate
            if (normalize && grandMeans[sid] > 0) mean = mean / grandMeans[sid];
            stageMeans.push(mean);
          });
          const barHeight = stageMeans.length > 0
            ? stageMeans.reduce((a, b) => a + b, 0) / stageMeans.length
            : 0;
          values.push(barHeight);

          // Error bars: SE of mean-normalized deviations
          if (showErrors) {
            const deviations = [];
            stageIds.forEach(sid => {
              const vals = dataIndex[p]?.[sid] || [];
              const gm = grandMeans[sid];
              vals.forEach(v => {
                let val = normalize && isAccuracy ? (1 - v) : v;
                if (normalize && gm > 0) val = val / gm;
                deviations.push(val - (normalize && gm > 0 ? (gm / gm) : gm));
              });
            });
            const devStats = stats(deviations);
            errors.push(devStats.se);
          } else {
            errors.push(0);
          }
        } else {
          // For absolute values, sum per run then average across runs
          // Only include stages whose effective protocol matches p
          const perRun = {};
          runs.forEach(r => {
            const sp = r.stage_protocols || {};
            let total = 0;
            let hasAny = false;
            (r.stages || []).forEach(s => {
              const stageProto = sp[s.stage_id] || s.protocol || r.protocol;
              if (stageProto !== p) return;
              if (s[metric] != null) { total += s[metric]; hasAny = true; }
            });
            if (!hasAny) return;
            perRun[r.run_id] = total;
          });
          const runTotals = Object.values(perRun);
          const s = stats(runTotals);
          values.push(s.mean);
          errors.push(showErrors ? s.se : 0);
        }
      });
      // Collect raw per-protocol values for scatter overlay
      const rawPerProto = protocols.map(p => {
        if (isRate || normalize) {
          // Collect normalized stage means per run (one value per run)
          const runVals = [];
          runs.forEach(r => {
            const sp = r.stage_protocols || {};
            const stageMeans = [];
            (r.stages || []).forEach(s => {
              const stageProto = sp[s.stage_id] || s.protocol || r.protocol;
              if (stageProto !== p) return;
              const v = s[metric];
              if (v == null) return;
              let val = normalize && isAccuracy ? (1 - v) : v;
              const sid = coalesce && taskFilter ? (getStageTag(taskFilter, s.stage_id) || s.stage_id) : s.stage_id;
              const gm = grandMeans[sid];
              if (normalize && gm > 0) val = val / gm;
              stageMeans.push(val);
            });
            if (stageMeans.length > 0) {
              runVals.push(stageMeans.reduce((a, b) => a + b, 0) / stageMeans.length);
            }
          });
          return runVals;
        } else {
          const perRun = [];
          runs.forEach(r => {
            const sp = r.stage_protocols || {};
            let total = 0, hasAny = false;
            (r.stages || []).forEach(s => {
              const stageProto = sp[s.stage_id] || s.protocol || r.protocol;
              if (stageProto !== p) return;
              if (s[metric] != null) { total += s[metric]; hasAny = true; }
            });
            if (hasAny) perRun.push(total);
          });
          return perRun;
        }
      });
      datasets = [{
        label: normalize ? `${metric} (normalized)` : metric,
        data: values,
        backgroundColor: VIZ_COLORS.slice(0, protocols.length),
        borderColor: VIZ_COLORS.slice(0, protocols.length),
        borderWidth: 1,
        rawValues: rawPerProto,
      }];
      if (showErrors) {
        datasets[0].errorBars = errors;
      }
    } else if (groupBy === 'stage') {
      // X-axis = stages, one dataset per protocol
      labels = stageIds.map(s => s.replace(/^\\d+_/, ''));
      datasets = protocols.map((proto, pi) => {
        const values = stageIds.map(sid => stats(dataIndex[proto]?.[sid]).mean);
        const errs = stageIds.map(sid => stats(dataIndex[proto]?.[sid]).se);
        const raw = stageIds.map(sid => dataIndex[proto]?.[sid] || []);
        return {
          label: proto,
          data: values,
          backgroundColor: VIZ_COLORS[pi % VIZ_COLORS.length] + 'cc',
          borderColor: VIZ_COLORS[pi % VIZ_COLORS.length],
          borderWidth: 1,
          errorBars: showErrors ? errs : null,
          rawValues: raw,
        };
      });
    } else {
      // X-axis = protocols, one dataset per stage
      labels = protocols;
      datasets = stageIds.map((sid, si) => {
        const values = protocols.map(p => stats(dataIndex[p]?.[sid]).mean);
        const errs = protocols.map(p => stats(dataIndex[p]?.[sid]).se);
        const raw = protocols.map(p => dataIndex[p]?.[sid] || []);
        return {
          label: sid.replace(/^\\d+_/, ''),
          data: values,
          backgroundColor: VIZ_COLORS[si % VIZ_COLORS.length] + 'cc',
          borderColor: VIZ_COLORS[si % VIZ_COLORS.length],
          borderWidth: 1,
          errorBars: showErrors ? errs : null,
          rawValues: raw,
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

    // Scatter overlay plugin: draw individual observations as jittered points
    const scatterOverlayPlugin = {
      id: 'scatterOverlay',
      afterDatasetsDraw(chart) {
        const c = chart.ctx;
        const yScale = chart.scales.y;
        chart.data.datasets.forEach((ds, di) => {
          if (!ds.rawValues) return;
          const meta = chart.getDatasetMeta(di);
          meta.data.forEach((bar, i) => {
            const vals = ds.rawValues[i];
            if (!vals || vals.length < 2) return; // no scatter needed for 0-1 points
            const xCenter = bar.x;
            const barW = bar.width || 20;
            const jitterRange = barW * 0.4; // spread within 40% of bar width
            const color = ds.borderColor instanceof Array ? ds.borderColor[i] : ds.borderColor;
            c.save();
            c.fillStyle = '#fff';
            c.globalAlpha = 0.7;
            // Deterministic jitter based on index
            vals.forEach((v, vi) => {
              const yPx = yScale.getPixelForValue(v);
              const jitter = (((vi * 7 + 3) % 11) / 10 - 0.5) * jitterRange;
              c.beginPath();
              c.arc(xCenter + jitter, yPx, 3, 0, 2 * Math.PI);
              c.fill();
            });
            c.globalAlpha = 0.9;
            c.strokeStyle = color;
            c.lineWidth = 1;
            vals.forEach((v, vi) => {
              const yPx = yScale.getPixelForValue(v);
              const jitter = (((vi * 7 + 3) % 11) / 10 - 0.5) * jitterRange;
              c.beginPath();
              c.arc(xCenter + jitter, yPx, 3, 0, 2 * Math.PI);
              c.stroke();
            });
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
            text: `${metric} ${viewMode === 'cumulative' ? '(cumulative)' : ''} ${coalesce ? '[coalesced by tags]' : ''} ${normalize && viewMode === 'cumulative' ? '[normalized]' : ''}`,
            color: '#e0e0e0',
            font: { size: 14 },
          },
        },
        scales: {
          x: { ticks: { color: '#888', maxRotation: 45 }, grid: { color: '#0f3460' } },
          y: {
            ticks: { color: '#888' },
            grid: { color: '#0f3460' },
            beginAtZero: true,
            title: {
              display: normalize && viewMode === 'cumulative',
              text: normalize && ['holdout_accuracy', 'training_accuracy'].includes(metric)
                ? 'relative error rate (1 = cross-protocol mean)'
                : (normalize ? 'relative to cross-protocol stage mean' : ''),
              color: '#aaa',
              font: { size: 11 },
            },
          },
        },
      },
      plugins: [errorBarPlugin, scatterOverlayPlugin],
    });

    // Update info panel
    const totalRuns = allRuns.length;
    const multiRun = protocols.some(p =>
      stageIds.some(sid => (dataIndex[p]?.[sid]?.length || 0) > 1)
    );
    let infoText = `${totalRuns} runs, ${protocols.length} protocols, ${stageIds.length} stages`;
    if (totalFailedRuns > 0 && !isFailedRunMetric) {
      infoText += ` (${totalFailedRuns} failed run${totalFailedRuns !== 1 ? 's' : ''} excluded)`;
    } else if (isFailedRunMetric) {
      infoText += ` (${totalFailedRuns} total failure${totalFailedRuns !== 1 ? 's' : ''} across all protocols)`;
    }
    if (multiRun) infoText += ' (multi-run data available)';
    document.getElementById('viz-info').textContent = infoText;
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

    // Baseline protocol selector
    const protocols = [...new Set(vizLogsData.map(r => r.protocol))].sort();
    const sel = document.getElementById('diff-baseline');
    sel.innerHTML = '';
    protocols.forEach(p => {
      const opt = document.createElement('option');
      opt.value = p; opt.textContent = p;
      sel.appendChild(opt);
    });
    if (protocols.length >= 1) {
      sel.value = protocols[0];
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
    const baseline = document.getElementById('diff-baseline').value;

    if (!taskPath) { alert('Select a task first.'); return; }

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
    const treatments = data.treatment_protocols || [];

    // Summary card
    const aStr = data.group_a.join(', ');
    const bStr = data.group_b.join(', ');
    html += `<div class="diff-result-card">
      <div class="diff-result-header">Differential: ${treatments.length} treatment${treatments.length !== 1 ? 's' : ''} vs ${data.baseline_protocol}</div>
      <div class="diff-stat"><span class="label">Group A (treatment)</span><span class="value">${aStr}</span></div>
      <div class="diff-stat"><span class="label">Group B (measured)</span><span class="value">${bStr}</span></div>
      <div class="diff-stat"><span class="label">Treatments</span><span class="value">${treatments.join(', ')}</span></div>
    </div>`;

    // Matched runs card
    html += '<div class="diff-result-card"><div class="diff-result-header">Matched Runs</div>';
    treatments.forEach(tp => {
      const tRuns = (data.treatment_runs || {})[tp] || [];
      html += `<div class="diff-stat"><span class="label">${tp}</span><span class="value">${tRuns.length > 0 ? tRuns.map(r => r.run_id).join(', ') : 'none'}</span></div>`;
    });
    const bRuns = data.baseline_runs || [];
    html += `<div class="diff-stat"><span class="label">Baseline (${data.baseline_protocol})</span><span class="value">${bRuns.length > 0 ? bRuns.map(r => r.run_id).join(', ') : 'none'}</span></div>`;
    html += '</div>';

    // Per-metric results
    const metricNames = Object.keys(data.results || {});
    metricNames.forEach(metric => {
      const r = data.results[metric];
      const b = r.baseline;
      const hasBaseline = b.mean !== null && b.mean !== undefined;

      html += `<div class="diff-result-card">
        <div class="diff-result-header">${metric}</div>`;

      if (hasBaseline) {
        html += `<div class="diff-stat"><span class="label">Baseline (${data.baseline_protocol}, n=${b.n})</span><span class="value">${b.mean.toFixed(4)} \\u00b1 ${(b.se || 0).toFixed(4)} SE</span></div>`;
      } else {
        html += '<div class="diff-stat"><span class="label">Baseline</span><span class="value" style="color:#ef4444;">No data</span></div>';
      }

      treatments.forEach(tp => {
        const tData = (r.treatments || {})[tp];
        if (!tData) return;
        const t = tData.stats;
        const hasTreatment = t.mean !== null && t.mean !== undefined;
        if (hasTreatment && hasBaseline) {
          const delta = tData.delta;
          const deltaStr = delta > 0 ? '+' + delta.toFixed(4) : delta.toFixed(4);
          const deltaClass = delta > 0 ? 'diff-delta-positive' : (delta < 0 ? 'diff-delta-negative' : '');
          html += `<div class="diff-stat"><span class="label">${tp} (n=${t.n})</span><span class="value">${t.mean.toFixed(4)} \\u00b1 ${(t.se || 0).toFixed(4)} SE &nbsp; <span class="${deltaClass}" style="font-weight:700;">${deltaStr}</span></span></div>`;
        } else if (!hasTreatment) {
          html += `<div class="diff-stat"><span class="label">${tp}</span><span class="value" style="color:#ef4444;">No data</span></div>`;
        }
      });
      html += '</div>';
    });

    // Per-metric charts
    html += `<div class="diff-result-card" style="font-size:12px;color:#888;">
      Bars show mean metric values on B stages only (stages ${bStr}).
      Each treatment bar = B-stage values from runs using that protocol on A stages (${aStr}) and ${data.baseline_protocol} on B.
      Baseline bar = B-stage values from runs using ${data.baseline_protocol} on all stages.
    </div>`;
    metricNames.forEach((m, mi) => {
      html += `<div class="diff-result-card"><div style="position:relative;height:220px;"><canvas id="diff-chart-${mi}"></canvas></div></div>`;
    });

    // Missing runs
    if (data.missing && data.missing.length > 0) {
      html += '<div class="diff-missing"><div class="diff-missing-title">Missing Runs</div>';
      data.missing.forEach(m => {
        html += `<div class="diff-missing-item">
          <div>${m.description}</div>`;
        if (m.fork_hint) {
          html += `<div style="margin-top:6px;padding:8px;background:#1a1a2e;border-radius:6px;font-size:12px;">
            <div style="color:#4ade80;margin-bottom:4px;">Setup: ${m.fork_hint.explanation}</div>
            <div style="color:#888;">A stages: [${m.fork_hint.a_stages.join(', ')}] → ${m.fork_hint.a_protocol}</div>
            <div style="color:#888;">B stages: [${m.fork_hint.b_stages.join(', ')}] → ${m.fork_hint.b_protocol}</div>
            <button class="btn-secondary" style="margin-top:6px;font-size:11px;padding:4px 10px;"
              onclick="setupDiffFork('${m.fork_hint.a_protocol}', '${m.fork_hint.b_protocol}')">Set Up This Run</button>
          </div>`;
        }
        html += '</div>';
      });
      html += '</div>';
    }

    resultsDiv.innerHTML = html;

    // Render per-metric diff charts
    if (diffChart) { diffChart.forEach(c => c.destroy()); }
    diffChart = [];

    const TREATMENT_COLORS = ['#e94560', '#f59e0b', '#10b981', '#8b5cf6', '#ec4899', '#06b6d4', '#84cc16'];
    const BASELINE_COLOR = '#3b82f6';

    const diffErrorBarPlugin = {
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

    metricNames.forEach((m, mi) => {
      const ctx = document.getElementById(`diff-chart-${mi}`);
      if (!ctx) return;
      const r = data.results[m];

      const labels = [...treatments, `Baseline (${data.baseline_protocol})`];
      const values = treatments.map(tp => ((r.treatments[tp] || {}).stats || {}).mean || 0);
      values.push(r.baseline.mean || 0);
      const errors = treatments.map(tp => ((r.treatments[tp] || {}).stats || {}).se || 0);
      errors.push(r.baseline.se || 0);
      const bgColors = treatments.map((_, i) => TREATMENT_COLORS[i % TREATMENT_COLORS.length] + 'cc');
      bgColors.push(BASELINE_COLOR + 'cc');
      const borderColors = treatments.map((_, i) => TREATMENT_COLORS[i % TREATMENT_COLORS.length]);
      borderColors.push(BASELINE_COLOR);

      const chart = new Chart(ctx.getContext('2d'), {
        type: 'bar',
        data: {
          labels: labels,
          datasets: [{
            label: m,
            data: values,
            backgroundColor: bgColors,
            borderColor: borderColors,
            borderWidth: 1,
            errorBars: errors,
          }],
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: {
            legend: { display: false },
            title: { display: true, text: m, color: '#e0e0e0', font: { size: 13 } },
          },
          scales: {
            x: { ticks: { color: '#888' }, grid: { color: '#0f3460' } },
            y: {
              ticks: { color: '#888' },
              grid: { color: '#0f3460' },
              beginAtZero: true,
              title: { display: true, text: m, color: '#aaa', font: { size: 11 } },
            },
          },
        },
        plugins: [diffErrorBarPlugin],
      });
      diffChart.push(chart);
    });
  }

  function setupDiffFork(aProto, bProto) {
    switchTab('experiment');
    showForkDialog();
    // Provide guidance in the fork dialog
    setTimeout(() => {
      const nodeInput = document.getElementById('fork-node-id');
      if (nodeInput) {
        nodeInput.placeholder = `Select a node, then set pipeline: A=${aProto}, B=${bProto}`;
      }
    }, 100);
  }

  // ---- Pareto Analysis ----

  const METRIC_DEFAULTS = {
    // Accuracies are converted to error rates for normalization, so lower is better
    'holdout_accuracy': 'lower', 'training_accuracy': 'lower',
    'regression_rate': 'lower', 'failed_run_pct': 'lower',
    'effective_tokens': 'lower',
    'total_tokens': 'lower', 'output_tokens': 'lower',
    'wall_time_seconds': 'lower', 'human_time_seconds': 'lower',
    'code_lines': 'lower', 'input_tokens': 'lower',
    'cache_creation_tokens': 'lower', 'cache_read_tokens': 'lower',
  };

  function populateParetoSelectors() {
    // Task selector
    const taskSel = document.getElementById('pareto-task');
    taskSel.innerHTML = '<option value="">All Tasks</option>';
    const taskNames = new Set();
    vizLogsData.forEach(r => { if (r.task) taskNames.add(r.task); });
    Object.keys(vizTasksData).forEach(t => taskNames.add(t));
    [...taskNames].sort().forEach(t => {
      const opt = document.createElement('option');
      opt.value = t;
      opt.textContent = vizTasksData[t]?.name || t.split('/').pop();
      taskSel.appendChild(opt);
    });

    // Baseline protocol selector
    const protocols = [...new Set(vizLogsData.map(r => r.protocol))].sort();
    const baseSel = document.getElementById('pareto-baseline');
    baseSel.innerHTML = '';
    protocols.forEach(p => {
      const opt = document.createElement('option');
      opt.value = p; opt.textContent = p;
      baseSel.appendChild(opt);
    });

    // Set default directions based on initial metric selections
    paretoSetDefaultDir('x');
    paretoSetDefaultDir('y');

    // Listen for metric changes to auto-set direction
    document.getElementById('pareto-x-metric').addEventListener('change', () => paretoSetDefaultDir('x'));
    document.getElementById('pareto-y-metric').addEventListener('change', () => paretoSetDefaultDir('y'));
  }

  function paretoSetDefaultDir(axis) {
    const metric = document.getElementById(`pareto-${axis}-metric`).value;
    const dirSel = document.getElementById(`pareto-${axis}-dir`);
    dirSel.value = METRIC_DEFAULTS[metric] || 'lower';
  }

  function paretoTaskChanged() {
    const taskPath = document.getElementById('pareto-task').value;
    const stageFilter = document.getElementById('pareto-stage-filter');
    stageFilter.innerHTML = '<option value="">All stages</option>';

    if (!taskPath) return;
    const task = vizTasksData[taskPath];
    if (!task || !task.stages) return;

    // Add per-stage options
    task.stages.forEach((s, i) => {
      const opt = document.createElement('option');
      opt.value = 'stage:' + s.id;
      opt.textContent = `Stage: ${s.id}`;
      stageFilter.appendChild(opt);
    });

    // Add tag options (from domain_tags and pipeline_tags)
    const allTags = new Set(task.domain_tags || []);
    task.stages.forEach(s => (s.pipeline_tags || []).forEach(t => allTags.add(t)));
    // Also gather pipeline-level tags
    Object.values(task.pipelines || {}).forEach(p => {
      (p.pipeline_tags || []).forEach(t => allTags.add(t));
    });
    [...allTags].sort().forEach(tag => {
      const opt = document.createElement('option');
      opt.value = 'tag:' + tag;
      opt.textContent = `Tag: ${tag}`;
      stageFilter.appendChild(opt);
    });

    // Also rebuild the differential stage selector
    paretoBuildDiffStages(task);
  }

  function paretoBuildDiffStages(task) {
    const container = document.getElementById('pareto-stage-selector');
    const presets = document.getElementById('pareto-presets');
    container.innerHTML = '';
    presets.innerHTML = '';
    if (!task || !task.stages) return;

    task.stages.forEach((stage, idx) => {
      const row = document.createElement('div');
      row.className = 'diff-stage-row';
      const name = `pareto_sg_${idx}`;
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

    const n = task.stages.length;
    for (let k = 1; k < n; k++) {
      const aStr = Array.from({length: k}, (_, i) => i + 1).join(',');
      const btn = document.createElement('button');
      btn.className = 'diff-preset-btn';
      btn.textContent = `A={${aStr}};B={${k + 1}}`;
      btn.onclick = () => {
        task.stages.forEach((_, idx) => {
          const radios = document.querySelectorAll(`input[name="pareto_sg_${idx}"]`);
          radios.forEach(r => {
            if (idx < k && r.value === 'a') r.checked = true;
            else if (idx === k && r.value === 'b') r.checked = true;
            else if (r.value === '') r.checked = (idx > k || (idx >= k && idx !== k));
          });
        });
      };
      presets.appendChild(btn);
    }
  }

  function paretoModeChanged() {
    const xDiff = document.getElementById('pareto-x-mode').value === 'differential';
    const yDiff = document.getElementById('pareto-y-mode').value === 'differential';
    document.getElementById('pareto-diff-config').style.display = (xDiff || yDiff) ? 'block' : 'none';
  }

  function paretoGetDiffGroups() {
    const taskPath = document.getElementById('pareto-task').value;
    const task = vizTasksData[taskPath];
    if (!task) return { a: [], b: [] };
    const a = [], b = [];
    task.stages.forEach((s, idx) => {
      const sel = document.querySelector(`input[name="pareto_sg_${idx}"]:checked`);
      if (sel && sel.value === 'a') a.push(s.id);
      else if (sel && sel.value === 'b') b.push(s.id);
    });
    return { a, b };
  }

  function matchStageId(logStageId, targetId) {
    return logStageId === targetId || logStageId.endsWith('_' + targetId);
  }

  function paretoStagePassesFilter(s, stageFilterVal) {
    if (s.skipped) return false;
    if (stageFilterVal) {
      if (stageFilterVal.startsWith('stage:')) {
        const sid = stageFilterVal.slice(6);
        if (!matchStageId(s.stage_id, sid)) return false;
      } else if (stageFilterVal.startsWith('tag:')) {
        const tag = stageFilterVal.slice(4);
        const taskPath = document.getElementById('pareto-task').value;
        const task = vizTasksData[taskPath];
        if (task) {
          const stageConf = task.stages.find(ts =>
            matchStageId(s.stage_id, ts.id)
          );
          if (!stageConf || !(stageConf.pipeline_tags || []).includes(tag)) return false;
        }
      }
    }
    return true;
  }

  // Compute normalized Pareto stats for all protocols at once.
  // For each (task, stage) bin, computes the cross-protocol mean, then
  // normalizes each protocol's per-bin mean by dividing by it. Accuracy
  // metrics are converted to error rates (1 - acc) before normalization
  // so that division is meaningful. The final mean/std per protocol is
  // taken across bins, ensuring equal weighting of all task×stage
  // combinations regardless of how many runs each has.
  function paretoComputeNormalized(metric, protocols, runs, stageFilterVal, allRuns) {
    const isAccuracy = ['holdout_accuracy', 'training_accuracy'].includes(metric);
    const result = {};

    // Special case: failed_run_pct is per-run, not per-stage
    if (metric === 'failed_run_pct') {
      protocols.forEach(proto => {
        const source = (allRuns || runs).filter(r => r.protocol === proto);
        if (source.length === 0) { result[proto] = null; return; }
        const failed = source.filter(r => r.total_failure).length;
        const pct = failed / source.length;
        const values = source.map(r => r.total_failure ? 1 : 0);
        let std = 0;
        if (values.length >= 2) {
          const variance = values.reduce((a, b) => a + (b - pct) ** 2, 0) / (values.length - 1);
          std = Math.sqrt(variance);
        }
        const binValues = {};
        source.forEach(r => { binValues[r.run_id || ''] = r.total_failure ? 1 : 0; });
        result[proto] = { mean: pct, std, n: values.length, binValues };
      });
      return result;
    }

    // Step 1: Collect observations grouped by (task, stage_id) bin and protocol.
    // For accuracy metrics, store as error rate (1 - acc).
    const binProtoVals = {}; // binKey -> { proto -> [values across runs] }
    runs.forEach(r => {
      const task = (r.task || '').replace(/\/$/, '');
      (r.stages || []).forEach(s => {
        if (!paretoStagePassesFilter(s, stageFilterVal)) return;
        const raw = s[metric];
        if (raw == null) return;
        const val = isAccuracy ? (1 - raw) : raw;
        const binKey = `${task}::${s.stage_id}`;
        if (!binProtoVals[binKey]) binProtoVals[binKey] = {};
        if (!binProtoVals[binKey][r.protocol]) binProtoVals[binKey][r.protocol] = [];
        binProtoVals[binKey][r.protocol].push(val);
      });
    });

    // Step 2: Cross-protocol mean for each bin (mean of per-protocol means,
    // so each protocol is weighted equally regardless of run count)
    const binGrandMeans = {};
    for (const [binKey, protoVals] of Object.entries(binProtoVals)) {
      const perProtoMeans = Object.values(protoVals).map(
        vals => vals.reduce((a, b) => a + b, 0) / vals.length
      );
      binGrandMeans[binKey] = perProtoMeans.reduce((a, b) => a + b, 0) / perProtoMeans.length;
    }

    // Step 3: Per protocol, compute normalized bin value (protocol's bin mean / grand mean),
    // then mean and std across bins.
    protocols.forEach(proto => {
      const binValues = {}; // binKey -> normalized mean for this protocol
      for (const [binKey, protoVals] of Object.entries(binProtoVals)) {
        const vals = protoVals[proto];
        if (!vals || vals.length === 0) continue;
        const rawMean = vals.reduce((a, b) => a + b, 0) / vals.length;
        const gm = binGrandMeans[binKey];
        binValues[binKey] = gm > 0 ? rawMean / gm : rawMean;
      }
      const values = Object.values(binValues);
      if (values.length === 0) { result[proto] = null; return; }
      const mean = values.reduce((a, b) => a + b, 0) / values.length;
      let std = 0;
      if (values.length >= 2) {
        const variance = values.reduce((a, b) => a + (b - mean) ** 2, 0) / (values.length - 1);
        std = Math.sqrt(variance);
      }
      result[proto] = { mean, std, n: values.length, binValues };
    });

    return result;
  }

  function paretoComputeDiff(protocol, metric, runs, baselineProto, aStages, bStages) {
    if (protocol === baselineProto) return { mean: 0, std: 0, n: 0, binValues: {} };

    function getStageProto(log, stageId) {
      const sp = log.stage_protocols || {};
      if (sp[stageId]) return sp[stageId];
      for (const s of (log.stages || [])) {
        if (matchStageId(s.stage_id, stageId))
          return s.protocol || log.protocol;
      }
      return log.protocol;
    }

    // Per-run treatment B-stage mean and baseline B-stage mean
    const treatmentRunVals = {}; // run_id -> mean of B-stage values
    const baselineRunVals = {};

    runs.forEach(log => {
      const protoMap = {};
      [...aStages, ...bStages].forEach(sid => {
        protoMap[sid] = getStageProto(log, sid);
      });

      const aTreatment = aStages.every(s => protoMap[s] === protocol);
      const bBaseline = bStages.every(s => protoMap[s] === baselineProto);
      const allBaseline = [...aStages, ...bStages].every(s => protoMap[s] === baselineProto);

      const rid = log.run_id || `_anon_${Math.random()}`;
      if (aTreatment && bBaseline) {
        const vals = [];
        bStages.forEach(sid => {
          const stage = (log.stages || []).find(s => matchStageId(s.stage_id, sid));
          if (stage && stage[metric] != null) vals.push(stage[metric]);
        });
        if (vals.length > 0) treatmentRunVals[rid] = vals.reduce((a, b) => a + b, 0) / vals.length;
      }
      if (allBaseline) {
        const vals = [];
        bStages.forEach(sid => {
          const stage = (log.stages || []).find(s => matchStageId(s.stage_id, sid));
          if (stage && stage[metric] != null) vals.push(stage[metric]);
        });
        if (vals.length > 0) baselineRunVals[rid] = vals.reduce((a, b) => a + b, 0) / vals.length;
      }
    });

    const tVals = Object.values(treatmentRunVals);
    const bVals = Object.values(baselineRunVals);
    if (tVals.length === 0 || bVals.length === 0) return null;
    const tMean = tVals.reduce((a, b) => a + b, 0) / tVals.length;
    const bMean = bVals.reduce((a, b) => a + b, 0) / bVals.length;
    const diffMean = tMean - bMean;
    // Propagate uncertainty: pooled std of per-run values
    let std = 0;
    const allVals = [...tVals, ...bVals];
    const n = allVals.length;
    if (n >= 2) {
      const pooledMean = allVals.reduce((a, b) => a + b, 0) / n;
      const variance = allVals.reduce((a, b) => a + (b - pooledMean) ** 2, 0) / (n - 1);
      std = Math.sqrt(variance);
    }
    // binValues: use treatment per-run means for covariance pairing
    return { mean: diffMean, std, n, binValues: treatmentRunVals };
  }

  function computeParetoFront(points, xHigherBetter, yHigherBetter) {
    const valid = points.filter(p => p.x != null && p.y != null && !isNaN(p.x) && !isNaN(p.y));
    if (valid.length === 0) return [];

    // Sort by x: best first
    valid.sort((a, b) => xHigherBetter ? b.x - a.x : a.x - b.x);

    const front = [];
    let bestY = yHigherBetter ? -Infinity : Infinity;
    for (const p of valid) {
      const dominated = yHigherBetter ? (p.y < bestY) : (p.y > bestY);
      if (!dominated) {
        front.push(p);
        bestY = p.y;
      }
    }

    // Sort front by x for drawing
    front.sort((a, b) => a.x - b.x);
    return front;
  }

  function renderParetoChart() {
    if (!vizLogsData) { alert('No data loaded yet.'); return; }

    const taskFilter = document.getElementById('pareto-task').value;
    const stageFilterVal = document.getElementById('pareto-stage-filter').value;
    const xMetric = document.getElementById('pareto-x-metric').value;
    const yMetric = document.getElementById('pareto-y-metric').value;
    const xMode = document.getElementById('pareto-x-mode').value;
    const yMode = document.getElementById('pareto-y-mode').value;
    const xDir = document.getElementById('pareto-x-dir').value;
    const yDir = document.getElementById('pareto-y-dir').value;
    const baselineProto = document.getElementById('pareto-baseline').value;

    const needsDiff = xMode === 'differential' || yMode === 'differential';
    let aStages = [], bStages = [];
    if (needsDiff) {
      if (!taskFilter) { alert('Select a task for differential mode.'); return; }
      const groups = paretoGetDiffGroups();
      aStages = groups.a;
      bStages = groups.b;
      if (aStages.length === 0 || bStages.length === 0) {
        alert('Assign at least one stage to group A and one to group B.'); return;
      }
    }

    // Filter runs (exclude total failures from normal metrics)
    let runs = vizLogsData;
    if (taskFilter) {
      runs = runs.filter(r => {
        const rt = (r.task || '').replace(/\\/$/, '');
        return rt === taskFilter || rt.endsWith('/' + taskFilter.split('/').pop());
      });
    }
    const allParetoRuns = runs; // keep unfiltered for failed_run_pct
    runs = runs.filter(r => !r.total_failure);

    // Get protocols (from all runs so failed-only protocols still appear for failed_run_pct)
    const protocols = [...new Set(allParetoRuns.map(r => r.protocol))].sort();

    // Precompute normalized stats for raw-mode metrics (batch across all protocols)
    const xNorm = xMode !== 'differential'
      ? paretoComputeNormalized(xMetric, protocols, runs, stageFilterVal, allParetoRuns) : null;
    const yNorm = yMode !== 'differential'
      ? paretoComputeNormalized(yMetric, protocols, runs, stageFilterVal, allParetoRuns) : null;

    // Compute points
    const points = [];
    const skipped = [];
    protocols.forEach(proto => {
      const xStats = xMode === 'differential'
        ? paretoComputeDiff(proto, xMetric, runs, baselineProto, aStages, bStages)
        : xNorm[proto];
      const yStats = yMode === 'differential'
        ? paretoComputeDiff(proto, yMetric, runs, baselineProto, aStages, bStages)
        : yNorm[proto];

      if (xStats == null || yStats == null) {
        skipped.push(proto);
      } else {
        // Compute covariance from paired bin values (keyed by task::stage or run_id)
        let cov = 0;
        const xBV = xStats.binValues || {};
        const yBV = yStats.binValues || {};
        const pairedIds = Object.keys(xBV).filter(k => k in yBV);
        if (pairedIds.length >= 2) {
          const xPaired = pairedIds.map(k => xBV[k]);
          const yPaired = pairedIds.map(k => yBV[k]);
          const xm = xPaired.reduce((a, b) => a + b, 0) / xPaired.length;
          const ym = yPaired.reduce((a, b) => a + b, 0) / yPaired.length;
          cov = xPaired.reduce((s, xi, i) => s + (xi - xm) * (yPaired[i] - ym), 0) / (pairedIds.length - 1);
        }
        points.push({
          protocol: proto,
          x: xStats.mean, y: yStats.mean,
          xStd: xStats.std, yStd: yStats.std,
          xN: xStats.n, yN: yStats.n,
          covXY: cov, nPaired: pairedIds.length,
        });
      }
    });

    if (points.length === 0) {
      document.getElementById('pareto-info').textContent = 'No data points. Check filters and ensure runs exist.';
      return;
    }

    // Compute Pareto front
    const front = computeParetoFront(points, xDir === 'higher', yDir === 'higher');

    // Build axis labels
    const isAccX = ['holdout_accuracy', 'training_accuracy'].includes(xMetric);
    const isAccY = ['holdout_accuracy', 'training_accuracy'].includes(yMetric);
    const xLabel = xMode === 'differential' ? `Δ ${xMetric}`
      : `${isAccX ? 'error rate' : xMetric} (normalized)`;
    const yLabel = yMode === 'differential' ? `Δ ${yMetric}`
      : `${isAccY ? 'error rate' : yMetric} (normalized)`;

    // Chart.js datasets
    const scatterData = points.map(p => ({ x: p.x, y: p.y }));
    const frontData = front.map(p => ({ x: p.x, y: p.y }));

    // Plugin to draw error ellipses and label points
    const paretoPlugins = {
      id: 'paretoOverlays',
      afterDatasetsDraw(chart) {
        const meta = chart.getDatasetMeta(0);
        const c = chart.ctx;
        const xScale = chart.scales.x;
        const yScale = chart.scales.y;

        // Draw error ellipses (±1 SE) with full covariance
        meta.data.forEach((pt, i) => {
          if (i >= points.length) return;
          const p = points[i];
          if (p.xN < 2 && p.yN < 2) return;

          const n = p.nPaired >= 2 ? p.nPaired : Math.min(p.xN, p.yN);
          if (n < 2) return;

          // Build 2x2 covariance-of-the-mean matrix (SE² terms)
          const varX = p.xN >= 2 ? (p.xStd * p.xStd) / p.xN : 0;
          const varY = p.yN >= 2 ? (p.yStd * p.yStd) / p.yN : 0;
          const covXY = p.nPaired >= 2 ? p.covXY / p.nPaired : 0;

          // Eigenvalues of [[varX, covXY],[covXY, varY]]
          const trace = varX + varY;
          const det = varX * varY - covXY * covXY;
          const disc = Math.sqrt(Math.max(trace * trace / 4 - det, 0));
          const lam1 = trace / 2 + disc;
          const lam2 = trace / 2 - disc;
          if (lam1 <= 0 && lam2 <= 0) return;

          // Rotation angle from eigenvector of larger eigenvalue
          let angle = 0;
          if (Math.abs(covXY) > 1e-15) {
            angle = Math.atan2(lam1 - varX, covXY);
          } else {
            angle = varX >= varY ? 0 : Math.PI / 2;
          }

          // ±1 SE radii in data space
          const seA = Math.sqrt(Math.max(lam1, 0));
          const seB = Math.sqrt(Math.max(lam2, 0));

          // Convert data-space SE to pixel-space radii
          const cx = pt.x;
          const cy = pt.y;
          // Pixel scale factors (may differ for x vs y)
          const pxPerX = Math.abs(xScale.getPixelForValue(1) - xScale.getPixelForValue(0));
          const pxPerY = Math.abs(yScale.getPixelForValue(1) - yScale.getPixelForValue(0));

          // Transform the ellipse axes to pixel space
          // The eigenvector gives direction (cos(angle), sin(angle)) in data space;
          // in pixel space that becomes (cos(angle)*pxPerX, sin(angle)*pxPerY)
          // We approximate by scaling the radii and adjusting the angle
          const cosA = Math.cos(angle), sinA = Math.sin(angle);
          const pixAngle = Math.atan2(sinA * pxPerY, cosA * pxPerX);
          const rA = Math.sqrt((seA * cosA * pxPerX) ** 2 + (seA * sinA * pxPerY) ** 2);
          const cosB = Math.cos(angle + Math.PI / 2), sinB = Math.sin(angle + Math.PI / 2);
          const rB = Math.sqrt((seB * cosB * pxPerX) ** 2 + (seB * sinB * pxPerY) ** 2);

          if (rA < 1 && rB < 1) return;

          const color = getProtocolColor(p.protocol);
          c.save();
          c.globalAlpha = 0.15;
          c.fillStyle = color;
          c.beginPath();
          c.ellipse(cx, cy, Math.max(rA, 2), Math.max(rB, 2), pixAngle, 0, 2 * Math.PI);
          c.fill();
          c.globalAlpha = 0.5;
          c.strokeStyle = color;
          c.lineWidth = 1.5;
          c.setLineDash([4, 3]);
          c.beginPath();
          c.ellipse(cx, cy, Math.max(rA, 2), Math.max(rB, 2), pixAngle, 0, 2 * Math.PI);
          c.stroke();
          c.restore();
        });

        // Draw point labels
        c.font = '11px system-ui, sans-serif';
        c.fillStyle = '#ccc';
        c.textAlign = 'left';
        c.textBaseline = 'bottom';
        meta.data.forEach((pt, i) => {
          if (i < points.length) {
            c.fillText(points[i].protocol, pt.x + 8, pt.y - 6);
          }
        });
      }
    };

    const ctx = document.getElementById('pareto-chart').getContext('2d');
    if (paretoChart) paretoChart.destroy();

    paretoChart = new Chart(ctx, {
      type: 'scatter',
      data: {
        datasets: [
          {
            label: 'Protocols',
            data: scatterData,
            backgroundColor: points.map(p => getProtocolColor(p.protocol)),
            borderColor: points.map(p => getProtocolColor(p.protocol)),
            pointRadius: 8,
            pointHoverRadius: 11,
          },
          {
            label: 'Pareto Front',
            data: frontData,
            type: 'line',
            borderColor: '#22c55eaa',
            borderDash: [6, 3],
            borderWidth: 2,
            pointRadius: 0,
            fill: false,
            tension: 0,
          }
        ]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { labels: { color: '#ccc' } },
          title: { display: true, text: `${yLabel} vs ${xLabel}`, color: '#e0e0e0', font: { size: 14 } },
          tooltip: {
            callbacks: {
              label: (ctx) => {
                if (ctx.datasetIndex === 0 && ctx.dataIndex < points.length) {
                  const p = points[ctx.dataIndex];
                  const lines = [`${p.protocol}: (${p.x.toFixed(4)}, ${p.y.toFixed(4)})`];
                  const xSE = p.xN >= 2 ? p.xStd / Math.sqrt(p.xN) : null;
                  const ySE = p.yN >= 2 ? p.yStd / Math.sqrt(p.yN) : null;
                  if (xSE != null) lines.push(`  x SE: ±${xSE.toFixed(4)} (n=${p.xN})`);
                  if (ySE != null) lines.push(`  y SE: ±${ySE.toFixed(4)} (n=${p.yN})`);
                  return lines;
                }
                return '';
              }
            }
          }
        },
        scales: {
          x: {
            title: { display: true, text: xLabel + (xDir === 'lower' ? ' (lower is better)' : ' (higher is better)'), color: '#888' },
            ticks: { color: '#888' }, grid: { color: '#0f3460' },
          },
          y: {
            title: { display: true, text: yLabel + (yDir === 'higher' ? ' (higher is better)' : ' (lower is better)'), color: '#888' },
            ticks: { color: '#888' }, grid: { color: '#0f3460' },
          },
        }
      },
      plugins: [paretoPlugins],
    });

    // Info panel
    let info = `${points.length} protocol${points.length !== 1 ? 's' : ''} plotted, ${front.length} on Pareto front.`;
    if (front.length > 0) {
      info += '\\nFront: ' + front.map(p => p.protocol).join(', ');
    }
    if (skipped.length > 0) {
      info += '\\nSkipped (no data): ' + skipped.join(', ');
    }
    document.getElementById('pareto-info').textContent = info;
  }

  // Init — load protocols first since buildStageProtocolList needs protocolsData
  initTerminal();
  loadProtocols().then(() => loadTasks());
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


def launch_ui(task_dir: str = None, protocol_name: str = None, host: str = "0.0.0.0",
              port: int = 8765, **kwargs):
    """Store config for deferred init and start the web server."""
    import uvicorn

    _global["task_dir"] = task_dir
    _global["current_task_name"] = Path(task_dir).name if task_dir else None
    _global["launch_kwargs"] = {
        k: v for k, v in kwargs.items()
        if k in ("engine_cmd", "model", "run_id", "work_dir", "log_dir")
    }
    _global["default_protocol"] = protocol_name

    # Migrate legacy root-level logs into per-task subdirectories
    _migrate_legacy_logs()

    # If both task and protocol were provided via CLI, initialize immediately
    if task_dir and protocol_name:
        session = init_experiment(task_dir, protocol_name, **_global["launch_kwargs"])
        # Store as the default session for tabs that connect without a session_id
        _global["default_session_id"] = session.session_id

    print(f"\n  Experiment UI: http://localhost:{port}\n")
    uvicorn.run(app, host=host, port=port, log_level="warning")
