"""Experiment runner: state machine that orchestrates a benchmark run.

This manages the workspace, invokes stages according to a protocol,
collects metrics, and writes structured logs. Designed to work with
Claude Code as the LLM interface.
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


def generate_claude_md(stage_id: str, protocol: ProtocolDef, has_full_spec: bool = False) -> str:
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


class Experiment:
    def __init__(self, task_dir, protocol_name, work_dir, log_dir, engine_cmd="python3 minidb.py"):
        self.task_dir = Path(task_dir)
        self.protocol = ALL_PROTOCOLS[protocol_name]
        self.work_dir = Path(work_dir)
        self.log_dir = Path(log_dir)
        self.test_dir = self.task_dir / "tests"

        # Load stages (and engine_cmd override) from task.yaml
        self.stages = self._load_stages()

        # Allow task.yaml to override engine_cmd when caller used the default
        if engine_cmd == "python3 minidb.py" and hasattr(self, '_task_engine_cmd'):
            self.engine_cmd = self._task_engine_cmd
        else:
            self.engine_cmd = engine_cmd

        self.completed_stages = []
        self.all_metrics = []
        self.git = None

        self.run_id = f"{protocol_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    def _load_stages(self):
        """Load stage IDs from task.yaml, with fallback for minidb."""
        task_yaml = self.task_dir / "task.yaml"
        if task_yaml.exists():
            with open(task_yaml) as f:
                task_cfg = yaml.safe_load(f)
            if "engine_cmd" in task_cfg:
                self._task_engine_cmd = task_cfg["engine_cmd"]
            stages = task_cfg.get("stages", [])
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

    def setup(self):
        """Initialize workspace and git repo."""
        self.work_dir.mkdir(parents=True, exist_ok=True)
        self.log_dir.mkdir(parents=True, exist_ok=True)

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

    def prepare_stage(self, stage_id):
        """Set up workspace for a stage: copy stage spec, generate CLAUDE.md, optionally copy tests."""
        stage_spec = self.task_dir / "stages" / f"{stage_id}.md"
        if stage_spec.exists():
            shutil.copy2(stage_spec, self.work_dir / "CURRENT_STAGE.md")

        # Copy training tests if protocol provides them
        if self.protocol.provides_training_tests:
            test_dest = self.work_dir / "tests"
            test_dest.mkdir(exist_ok=True)
            # Copy conftest
            conftest = self.test_dir / "conftest.py"
            if conftest.exists():
                shutil.copy2(conftest, test_dest / "conftest.py")
            # Copy training tests for this stage
            training_dir = self.test_dir / "training"
            for f in training_dir.iterdir():
                if stage_id.replace("_", "") in f.name.replace("_", "") or stage_id in f.name:
                    shutil.copy2(f, test_dest / f.name)

        # Generate CLAUDE.md for the workspace
        has_full_spec = self.protocol.provides_full_spec and (self.work_dir / "spec.md").exists()
        claude_md = generate_claude_md(stage_id, self.protocol, has_full_spec=has_full_spec)
        (self.work_dir / "CLAUDE.md").write_text(claude_md)

        print(f"\n{'='*60}")
        print(f"STAGE: {stage_id}")
        print(f"PROTOCOL: {self.protocol.name} (model: {self.protocol.model})")
        print(f"{'='*60}")

        if self.protocol.added_instructions:
            print(f"\nINSTRUCTIONS TO LLM:\n{self.protocol.added_instructions}")

        if self.protocol.planning_phase:
            print(f"\nPLANNING PROMPT:\n{self.protocol.planning_prompt}")

        if self.protocol.human_supervised:
            print(f"\nHUMAN INSTRUCTIONS:\n{self.protocol.human_instructions}")

        print(f"\nStage spec: {self.work_dir / 'CURRENT_STAGE.md'}")
        if self.protocol.provides_training_tests:
            print(f"Tests: {self.work_dir / 'tests'}")
        print(f"CLAUDE.md: {self.work_dir / 'CLAUDE.md'}")
        print(f"\nWork in: {self.work_dir}")

    def build_stage_prompt(self, stage_id: str) -> str:
        """Build the implementation prompt to send to Claude for a stage.

        Note: for planning-phase protocols, the planning prompt is handled
        separately by claude_runner (first invocation in plan mode). This
        method builds the implementation prompt only.
        """
        parts = []

        if self.protocol.added_instructions:
            parts.append(self.protocol.added_instructions)
            parts.append("")

        parts.append(f"The current stage is: {stage_id}")
        parts.append("Read CURRENT_STAGE.md for the stage specification.")

        if self.protocol.provides_full_spec:
            parts.append("The full specification is in spec.md for reference.")

        if self.protocol.provides_training_tests:
            parts.append("Run the tests in tests/ and iterate until they pass.")

        return "\n".join(parts)

    def complete_stage(self, stage_id, human_time=0.0, wall_time=None, token_data=None):
        """Run metrics collection after a stage is done.

        Args:
            stage_id: The stage identifier.
            human_time: Active human time in seconds (presence-tracked).
            wall_time: Total wall-clock time in seconds. Defaults to human_time
                      if not provided (backward compat for non-UI modes).
            token_data: Optional dict with input_tokens, output_tokens,
                       total_tokens, cache_read_tokens, cache_creation_tokens.
        """
        # Git commit
        commit = self.git.commit_all(f"Stage {stage_id} complete ({self.protocol.name})")
        self.git.tag(f"{self.run_id}/{stage_id}")

        # Collect metrics
        metrics = collect_stage_metrics(
            stage_id=stage_id,
            protocol=self.protocol.name,
            project_dir=str(self.work_dir),
            test_dir=str(self.test_dir),
            engine_cmd=f"cd {self.work_dir} && {self.engine_cmd}",
            previous_stages=list(self.completed_stages),
        )
        metrics.human_time_seconds = human_time
        metrics.wall_time_seconds = wall_time if wall_time is not None else human_time
        metrics.git_commit = commit
        metrics.git_tag = f"{self.run_id}/{stage_id}"

        # Apply token data
        if token_data:
            metrics.input_tokens = token_data.get("input_tokens", 0)
            metrics.output_tokens = token_data.get("output_tokens", 0)
            metrics.total_tokens = token_data.get("total_tokens", 0)
            metrics.cache_read_tokens = token_data.get("cache_read_tokens", 0)
            metrics.cache_creation_tokens = token_data.get("cache_creation_tokens", 0)

        self.completed_stages.append(stage_id)
        self.all_metrics.append(metrics)

        # Print summary
        print(f"\n--- Stage {stage_id} metrics ---")
        print(f"  Training: {metrics.training_tests_passed}/{metrics.training_tests_total}")
        print(f"  Holdout:  {metrics.holdout_tests_passed}/{metrics.holdout_tests_total}")
        print(f"  Regression: {metrics.regression_tests_failed}/{metrics.regression_tests_total} failures")
        print(f"  Code: {metrics.code_lines} lines")
        print(f"  Human time: {metrics.human_time_seconds:.0f}s")
        print(f"  Tokens: {metrics.total_tokens} (in={metrics.input_tokens}, out={metrics.output_tokens})")

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
        log_path = self.log_dir / f"{self.run_id}.json"
        with open(log_path, "w") as f:
            json.dump(log, f, indent=2, default=str)
        print(f"\nLog saved to {log_path}")
        return log_path
