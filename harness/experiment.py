"""Experiment runner: state machine that orchestrates a benchmark run.

This manages the workspace, invokes stages according to a protocol,
collects metrics, and writes structured logs. Designed to work with
Claude Code as the LLM interface.

Supports pipeline-driven execution with per-stage protocol slots,
special stage types (translate/refactor/removal), and git-based forking
from existing experiment states.
"""
import json
import os
import time
import shutil
import yaml
from datetime import datetime
from pathlib import Path
from .metrics import collect_stage_metrics, detect_merge_conflicts, StageMetrics
from .git_manager import GitManager
from .protocols import ALL_PROTOCOLS, ProtocolDef
from .stage_types import (
    is_special_stage, parse_special_stage, build_prompt as build_special_prompt,
    get_test_strategy, get_stage_description,
)
from .state_tree import StateTree


def generate_claude_md(stage_id: str, protocol: ProtocolDef, has_full_spec: bool = False,
                       special_stage: dict = None) -> str:
    """Generate a CLAUDE.md file for a stage.

    Contains protocol instructions and references to spec/stage files
    so the Claude session knows what to do.
    """
    lines = []
    lines.append("# Instructions")
    lines.append("")

    if protocol.added_instructions:
        lines.append(protocol.added_instructions)
        lines.append("")

    if special_stage:
        desc = get_stage_description(special_stage["type"], special_stage["target"])
        lines.append(f"## Current Task: {desc}")
        lines.append("")
        lines.append("This is a transformation stage. Follow the prompt instructions carefully.")
        lines.append("")
    else:
        lines.append("## Reference Files")
        lines.append("- Read `CURRENT_STAGE.md` for the current stage requirements.")
        if has_full_spec:
            lines.append("- Read `spec.md` for the full specification.")
        lines.append("")

    if protocol.provides_training_tests:
        lines.append("- Tests are in the `tests/` directory. Run them with `python3 -m pytest tests/ -v`.")
        lines.append("")

    lines.append("## Constraints")
    lines.append("- Work only on files in the current directory.")
    lines.append("- Do not create or modify test files unless you are writing your own tests.")
    if special_stage:
        lines.append(f"- Focus on the {special_stage['type']} operation described in the prompt.")
    else:
        lines.append("- Focus on implementing the current stage specification.")
    lines.append("")

    return "\n".join(lines)


def setup_run_directory(run_id: str, task_dir: str, protocol: ProtocolDef) -> dict:
    """Create the isolated run directory structure.

    Creates:
        runs/<run_id>/
            workspace/    — isolated working dir for Claude
            results/      — metrics, logs, plots

    Only copies spec.md if protocol.provides_full_spec is True.

    Returns dict with 'workspace' and 'results' paths.
    """
    task_dir = Path(task_dir)
    base = Path("runs") / run_id
    workspace = base / "workspace"
    results = base / "results"

    workspace.mkdir(parents=True, exist_ok=True)
    results.mkdir(parents=True, exist_ok=True)

    # Only copy full spec if the protocol says to
    if protocol.provides_full_spec:
        spec_src = task_dir / "spec.md"
        if spec_src.exists():
            shutil.copy2(spec_src, workspace / "spec.md")

    return {
        "workspace": str(workspace),
        "results": str(results),
    }


def load_task_config(task_dir) -> dict:
    """Load task.yaml and return the full config dict."""
    task_yaml = Path(task_dir) / "task.yaml"
    if task_yaml.exists():
        with open(task_yaml) as f:
            return yaml.safe_load(f)
    return {}


def resolve_pipeline(task_cfg: dict, pipeline_name: str, slots: dict = None) -> list:
    """Resolve a pipeline definition into a list of stage descriptors.

    Each descriptor is a dict with:
      - stage_id: str (e.g. "01_select_where" or "translate_cpp")
      - type: "feature" | "translate" | "refactor" | "removal" | "parallel"
      - slot: str or None (protocol slot label like "A", "B")
      - target: str or None (for special stages)
      - parallel: list or None (for parallel stages)

    Args:
        task_cfg: Parsed task.yaml dict.
        pipeline_name: Name of the pipeline in task_cfg["pipelines"].
        slots: Optional dict mapping slot labels to protocol names.
    """
    pipelines = task_cfg.get("pipelines", {})
    if pipeline_name not in pipelines:
        raise ValueError(f"Pipeline '{pipeline_name}' not found. Available: {list(pipelines.keys())}")

    pipeline = pipelines[pipeline_name]
    raw_stages = pipeline.get("stages", [])
    slots = slots or {}

    # Build a lookup from stage id -> numbered stage id
    stage_id_map = {}
    for i, s in enumerate(task_cfg.get("stages", []), 1):
        sid = s["id"]
        stage_id_map[sid] = f"{i:02d}_{sid}"

    resolved = []
    for entry in raw_stages:
        if isinstance(entry, str):
            # Simple stage reference: "select_where"
            resolved.append({
                "stage_id": stage_id_map.get(entry, entry),
                "type": "feature",
                "slot": None,
                "target": None,
                "parallel": None,
            })
        elif isinstance(entry, dict):
            # Check for special stage types first (translate/refactor/removal)
            if is_special_stage(entry):
                special = parse_special_stage(entry)
                resolved.append({
                    "stage_id": special["id"],
                    "type": special["type"],
                    "slot": entry.get("slot"),
                    "target": special["target"],
                    "parallel": None,
                })
            # Check for slot assignment: {stage: "select_where", slot: "A"}
            elif "stage" in entry:
                sid = entry["stage"]
                resolved.append({
                    "stage_id": stage_id_map.get(sid, sid),
                    "type": "feature",
                    "slot": entry.get("slot"),
                    "target": None,
                    "parallel": None,
                })
            # Check for parallel block: {parallel: [order_limit, aggregation]}
            elif "parallel" in entry:
                par_stages = entry["parallel"]
                resolved.append({
                    "stage_id": f"parallel_{'_'.join(par_stages)}",
                    "type": "parallel",
                    "slot": None,
                    "target": None,
                    "parallel": [stage_id_map.get(s, s) for s in par_stages],
                })
            else:
                raise ValueError(f"Unknown pipeline stage format: {entry}")

    return resolved


class Experiment:
    def __init__(self, task_dir, protocol_name, work_dir, log_dir,
                 engine_cmd="python3 minidb.py", pipeline_name=None,
                 slots=None):
        self.task_dir = Path(task_dir)
        self.protocol = ALL_PROTOCOLS[protocol_name]
        self.protocol_name = protocol_name
        self.work_dir = Path(work_dir)
        self.log_dir = Path(log_dir)
        self.test_dir = self.task_dir / "tests"

        # Load task config
        self.task_cfg = load_task_config(task_dir)

        # Pipeline support
        self.pipeline_name = pipeline_name
        self.slots = slots or {}  # {slot_label: protocol_name}
        self.pipeline_stages = None  # resolved pipeline descriptors

        # Load stages (and engine_cmd override) from task.yaml
        self.stages = self._load_stages()

        # Allow task.yaml to override engine_cmd when caller used the default
        if engine_cmd == "python3 minidb.py" and "engine_cmd" in self.task_cfg:
            self.engine_cmd = self.task_cfg["engine_cmd"]
        else:
            self.engine_cmd = engine_cmd

        self.completed_stages = []
        self.all_metrics = []
        self.git = None

        # State tree for tracking experiment DAG
        self.state_tree = StateTree(str(self.log_dir))
        self._last_tree_node = None  # most recently added tree node

        # Per-stage protocol map (for mixed-protocol runs)
        self._stage_protocols = {}  # stage_id -> ProtocolDef

        self.run_id = f"{protocol_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        # If pipeline specified, resolve it
        if pipeline_name:
            self.pipeline_stages = resolve_pipeline(self.task_cfg, pipeline_name, slots)
            self._resolve_stage_protocols()

    def _load_stages(self):
        """Load stage IDs from task.yaml, with fallback for minidb."""
        stages = self.task_cfg.get("stages", [])
        if stages:
            # Build stage IDs matching the stage file naming: NN_id
            result = []
            for i, s in enumerate(stages, 1):
                sid = s["id"]
                # Check if stage files use numbered prefix
                numbered = f"{i:02d}_{sid}"
                stage_file = self.task_dir / "stages" / f"{numbered}.md"
                if stage_file.exists():
                    result.append(numbered)
                else:
                    result.append(sid)
            return result
        # Fallback: hardcoded minidb stages
        return [
            "01_select_where", "02_order_limit", "03_aggregation",
            "04_join", "05_list_ops", "06_coercion",
        ]

    def _resolve_stage_protocols(self):
        """Resolve per-stage protocols from pipeline slot assignments."""
        if not self.pipeline_stages:
            return
        for ps in self.pipeline_stages:
            slot = ps.get("slot")
            if slot and slot in self.slots:
                proto_name = self.slots[slot]
                if proto_name in ALL_PROTOCOLS:
                    self._stage_protocols[ps["stage_id"]] = ALL_PROTOCOLS[proto_name]

    def get_protocol_for_stage(self, stage_id: str) -> ProtocolDef:
        """Get the protocol to use for a given stage (supports per-stage overrides)."""
        return self._stage_protocols.get(stage_id, self.protocol)

    def get_pipeline_config(self) -> dict:
        """Get the raw pipeline config from task.yaml, or None."""
        if not self.pipeline_name:
            return None
        return self.task_cfg.get("pipelines", {}).get(self.pipeline_name)

    def get_pipeline_stages_list(self) -> list:
        """Get the list of stage IDs to execute for the current pipeline or default."""
        if self.pipeline_stages:
            result = []
            for ps in self.pipeline_stages:
                if ps["type"] == "parallel":
                    # For parallel stages, add them individually
                    result.extend(ps["parallel"])
                else:
                    result.append(ps["stage_id"])
            return result
        return list(self.stages)

    def setup(self, fork_from_node=None):
        """Initialize workspace and git repo.

        Args:
            fork_from_node: Optional node_id to fork from. If provided, checks
                out the git tag of that node instead of starting fresh.
        """
        self.work_dir.mkdir(parents=True, exist_ok=True)
        self.log_dir.mkdir(parents=True, exist_ok=True)

        if fork_from_node:
            self._fork_from(fork_from_node)
        else:
            self.git = GitManager(str(self.work_dir))
            self.git.init()

            # Only copy full spec if protocol provides it
            if self.protocol.provides_full_spec:
                spec_src = self.task_dir / "spec.md"
                if spec_src.exists():
                    shutil.copy2(spec_src, self.work_dir / "spec.md")

            self.git.commit_all("Initial: empty workspace")

        print(f"Experiment {self.run_id} initialized in {self.work_dir}")
        print(f"  Model: {self.protocol.model}")
        print(f"  Full spec: {'yes' if self.protocol.provides_full_spec else 'no (stage-only)'}")
        if self.pipeline_name:
            print(f"  Pipeline: {self.pipeline_name}")
            if self.slots:
                print(f"  Slots: {self.slots}")
        if fork_from_node:
            print(f"  Forked from: {fork_from_node}")

    def _fork_from(self, node_id: str):
        """Fork workspace from an existing experiment tree node.

        Looks up the node's git tag, clones/checks out that state into
        the workspace, and marks completed stages from the fork path.
        """
        node = self.state_tree.find_by_id(node_id)
        if not node:
            raise ValueError(f"Node '{node_id}' not found in experiment tree")

        # Get the path to this node to know which stages are already done
        path = self.state_tree.get_path(node_id)

        # We need to find the git repo that has this tag.
        # The tag format is run_id/stage_id. We look in existing run dirs.
        git_tag = node.git_tag

        # Initialize git in work_dir
        self.git = GitManager(str(self.work_dir))

        # Check if work_dir already has a git repo with this tag
        try:
            self.git._run("rev-parse", "--git-dir")
            has_repo = True
        except RuntimeError:
            has_repo = False

        if not has_repo:
            self.git.init()

        # Try to find and fetch from the source repo
        # The source repo is likely in runs/<run_id>/workspace/
        source_run_id = node.run_id
        source_workspace = Path("runs")
        # Search for the workspace that has this tag
        found_source = None
        for run_dir in source_workspace.iterdir() if source_workspace.exists() else []:
            ws = run_dir / "workspace"
            if ws.is_dir():
                try:
                    result = GitManager(str(ws))
                    result._run("tag", "-l", git_tag)
                    tags = result._run("tag", "-l").splitlines()
                    if git_tag in tags:
                        found_source = str(ws)
                        break
                except RuntimeError:
                    continue

        if found_source:
            # Fetch from source and checkout
            try:
                self.git._run("remote", "add", "source", found_source)
            except RuntimeError:
                self.git._run("remote", "set-url", "source", found_source)
            self.git._run("fetch", "source", "--tags")
            branch_name = f"fork_{node_id}_{int(time.time())}"
            self.git._run("checkout", git_tag, "-b", branch_name)
            print(f"  Forked from {git_tag} on branch {branch_name}")
        else:
            print(f"  WARNING: Could not find source repo with tag {git_tag}")
            print(f"  Starting fresh (fork point not available)")
            self.git.commit_all("Initial: empty workspace (fork source not found)")
            return

        # Mark stages from the fork path as completed
        for fork_node in path:
            self.completed_stages.append(fork_node.stage_id)
            self._last_tree_node = fork_node

    def prepare_stage(self, stage_id, special_stage=None):
        """Set up workspace for a stage: copy stage spec, generate CLAUDE.md, optionally copy tests.

        Args:
            stage_id: The stage identifier.
            special_stage: Optional dict with {type, target, id} for special stages.
        """
        protocol = self.get_protocol_for_stage(stage_id)

        if special_stage:
            # Special stage: write the prompt as CURRENT_STAGE.md
            prompt = build_special_prompt(special_stage["type"], special_stage["target"])
            (self.work_dir / "CURRENT_STAGE.md").write_text(prompt)
        else:
            stage_spec = self.task_dir / "stages" / f"{stage_id}.md"
            if stage_spec.exists():
                shutil.copy2(stage_spec, self.work_dir / "CURRENT_STAGE.md")

        # Copy training tests if protocol provides them
        if protocol.provides_training_tests:
            test_dest = self.work_dir / "tests"
            test_dest.mkdir(exist_ok=True)
            # Copy conftest
            conftest = self.test_dir / "conftest.py"
            if conftest.exists():
                shutil.copy2(conftest, test_dest / "conftest.py")

            if special_stage and get_test_strategy(special_stage["type"]) == "exclude_target":
                # Removal: copy all tests EXCEPT the target stage's tests
                training_dir = self.test_dir / "training"
                target_stage = special_stage["target"]
                for f in training_dir.iterdir() if training_dir.is_dir() else []:
                    if target_stage not in f.name and f.name.endswith(".py"):
                        shutil.copy2(f, test_dest / f.name)
            elif special_stage:
                # translate/refactor: copy ALL existing tests (same tests must pass)
                training_dir = self.test_dir / "training"
                for f in training_dir.iterdir() if training_dir.is_dir() else []:
                    if f.name.endswith(".py"):
                        shutil.copy2(f, test_dest / f.name)
            else:
                # Normal feature stage: copy training tests for this stage
                training_dir = self.test_dir / "training"
                for f in training_dir.iterdir() if training_dir.is_dir() else []:
                    if stage_id.replace("_", "") in f.name.replace("_", "") or stage_id in f.name:
                        shutil.copy2(f, test_dest / f.name)

        # Generate CLAUDE.md for the workspace
        has_full_spec = protocol.provides_full_spec and (self.work_dir / "spec.md").exists()
        claude_md = generate_claude_md(stage_id, protocol, has_full_spec=has_full_spec,
                                       special_stage=special_stage)
        (self.work_dir / "CLAUDE.md").write_text(claude_md)

        print(f"\n{'='*60}")
        print(f"STAGE: {stage_id}")
        if special_stage:
            desc = get_stage_description(special_stage["type"], special_stage["target"])
            print(f"TYPE: {desc}")
        print(f"PROTOCOL: {protocol.name} (model: {protocol.model})")
        print(f"{'='*60}")

        if protocol.added_instructions:
            print(f"\nINSTRUCTIONS TO LLM:\n{protocol.added_instructions}")

        if protocol.planning_phase:
            print(f"\nPLANNING PROMPT:\n{protocol.planning_prompt}")

        if protocol.human_supervised:
            print(f"\nHUMAN INSTRUCTIONS:\n{protocol.human_instructions}")

        print(f"\nStage spec: {self.work_dir / 'CURRENT_STAGE.md'}")
        if protocol.provides_training_tests:
            print(f"Tests: {self.work_dir / 'tests'}")
        print(f"CLAUDE.md: {self.work_dir / 'CLAUDE.md'}")
        print(f"\nWork in: {self.work_dir}")

    def build_stage_prompt(self, stage_id: str, special_stage: dict = None) -> str:
        """Build the implementation prompt to send to Claude for a stage.

        Note: for planning-phase protocols, the planning prompt is handled
        separately by claude_runner (first invocation in plan mode). This
        method builds the implementation prompt only.
        """
        protocol = self.get_protocol_for_stage(stage_id)
        parts = []

        if protocol.added_instructions:
            parts.append(protocol.added_instructions)
            parts.append("")

        if special_stage:
            prompt = build_special_prompt(special_stage["type"], special_stage["target"])
            parts.append(prompt)
        else:
            parts.append(f"The current stage is: {stage_id}")
            parts.append("Read CURRENT_STAGE.md for the stage specification.")

            if protocol.provides_full_spec:
                parts.append("The full specification is in spec.md for reference.")

        if protocol.provides_training_tests:
            parts.append("Run the tests in tests/ and iterate until they pass.")

        return "\n".join(parts)

    def complete_stage(self, stage_id, human_time=0.0, wall_time=None, token_data=None,
                       stage_index=None):
        """Run metrics collection after a stage is done.

        Args:
            stage_id: The stage identifier.
            human_time: Active human time in seconds (presence-tracked).
            wall_time: Total wall-clock time in seconds. Defaults to human_time
                      if not provided (backward compat for non-UI modes).
            token_data: Optional dict with input_tokens, output_tokens,
                       total_tokens, cache_read_tokens, cache_creation_tokens.
            stage_index: Optional stage index in the pipeline for tree recording.
        """
        protocol = self.get_protocol_for_stage(stage_id)

        # Git commit
        commit = self.git.commit_all(f"Stage {stage_id} complete ({protocol.name})")
        git_tag = f"{self.run_id}/{stage_id}"
        self.git.tag(git_tag)

        # Collect metrics
        metrics = collect_stage_metrics(
            stage_id=stage_id,
            protocol=protocol.name,
            project_dir=str(self.work_dir),
            test_dir=str(self.test_dir),
            engine_cmd=f"cd {self.work_dir} && {self.engine_cmd}",
            previous_stages=list(self.completed_stages),
        )
        metrics.human_time_seconds = human_time
        metrics.wall_time_seconds = wall_time if wall_time is not None else human_time
        metrics.git_commit = commit
        metrics.git_tag = git_tag

        # Apply token data
        if token_data:
            metrics.input_tokens = token_data.get("input_tokens", 0)
            metrics.output_tokens = token_data.get("output_tokens", 0)
            metrics.total_tokens = token_data.get("total_tokens", 0)
            metrics.cache_read_tokens = token_data.get("cache_read_tokens", 0)
            metrics.cache_creation_tokens = token_data.get("cache_creation_tokens", 0)

        self.completed_stages.append(stage_id)
        self.all_metrics.append(metrics)

        # Record in state tree
        parent_id = self._last_tree_node.node_id if self._last_tree_node else None
        tree_node = self.state_tree.add_node(
            git_tag=git_tag,
            stage_id=stage_id,
            protocol=protocol.name,
            parent=parent_id,
            run_id=self.run_id,
            metrics_log=f"{self.run_id}.json",
            stage_index=stage_index if stage_index is not None else len(self.completed_stages) - 1,
        )
        self._last_tree_node = tree_node

        # Print summary
        print(f"\n--- Stage {stage_id} metrics ---")
        print(f"  Protocol: {protocol.name}")
        print(f"  Training: {metrics.training_tests_passed}/{metrics.training_tests_total}")
        print(f"  Holdout:  {metrics.holdout_tests_passed}/{metrics.holdout_tests_total}")
        print(f"  Regression: {metrics.regression_tests_failed}/{metrics.regression_tests_total} failures")
        print(f"  Code: {metrics.code_lines} lines")
        print(f"  Human time: {metrics.human_time_seconds:.0f}s")
        print(f"  Tokens: {metrics.total_tokens} (in={metrics.input_tokens}, out={metrics.output_tokens})")
        print(f"  Tree node: {tree_node.node_id}")

        return metrics

    def run_parallel_stages(self, base_stage, parallel_stages):
        """Run two stages in parallel branches and merge."""
        base_commit = self.git.current_commit()

        branch_metrics = {}
        for stage_id in parallel_stages:
            self.git.checkout(base_commit)
            branch_name = f"{self.run_id}/{stage_id}"
            self.git.branch(branch_name)
            self.prepare_stage(stage_id)

            input(f"\nComplete stage {stage_id} on branch {branch_name}, then press Enter...")
            # TODO: capture human time
            metrics = self.complete_stage(stage_id)
            branch_metrics[stage_id] = metrics

        # Merge
        self.git.checkout(f"{self.run_id}/{parallel_stages[0]}")
        for stage_id in parallel_stages[1:]:
            branch_name = f"{self.run_id}/{stage_id}"
            success, conflicts = self.git.merge(branch_name, no_commit=True)

            if not success:
                n_conflicts, conflict_files = detect_merge_conflicts(str(self.work_dir))
                print(f"\nMERGE CONFLICTS: {n_conflicts} in {conflict_files}")
                print("Resolve conflicts, then press Enter...")
                input()
                self.git.commit_all(f"Merge {stage_id} (conflicts resolved)")
            else:
                self.git.commit_all(f"Merge {stage_id} (clean)")

            # Record merge metrics
            for m in branch_metrics.values():
                m.merge_conflicts = conflicts

        return branch_metrics

    def save_log(self):
        """Write all metrics to a structured JSON log."""
        log = {
            "run_id": self.run_id,
            "protocol": self.protocol.name,
            "model": self.protocol.model,
            "task": str(self.task_dir),
            "timestamp": datetime.now().isoformat(),
            "stages": [m.to_dict() for m in self.all_metrics],
        }

        # Add pipeline info if running a pipeline
        if self.pipeline_name:
            pipeline_cfg = self.get_pipeline_config()
            log["pipeline"] = self.pipeline_name
            log["slots"] = self.slots
            if pipeline_cfg:
                log["pipeline_config"] = pipeline_cfg
            # Per-stage protocol map
            log["stage_protocols"] = {
                sid: proto.name for sid, proto in self._stage_protocols.items()
            }

        log_path = self.log_dir / f"{self.run_id}.json"
        with open(log_path, "w") as f:
            json.dump(log, f, indent=2, default=str)
        print(f"\nLog saved to {log_path}")
        return log_path
