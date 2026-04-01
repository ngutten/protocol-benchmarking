#!/usr/bin/env python3
"""Retroactively correct token counts in results/logs to include sub-agent usage.

For each benchmark run, finds the corresponding Claude session files, sums up
any sub-agent token usage that was missed, and patches both the results JSON
(in runs/<task>/<run>/results/) and the log JSON (in logs/<task>/).

Two strategies depending on whether session_ids are recorded in phase_breakdown:

1. Runs WITH session_ids in phase_breakdown: correct each phase individually,
   then recompute stage totals from the corrected phases.

2. Runs WITHOUT session_ids (older format): scan all session files in the
   project directory, sum all sub-agent tokens, and add them to each stage
   proportionally (by the stage's share of the run's parent output tokens).

Usage:
    python fix_subagent_tokens.py              # dry-run, print what would change
    python fix_subagent_tokens.py --apply      # write corrected files
"""
import argparse
import json
import os
import sys
from pathlib import Path

HARNESS_DIR = Path(__file__).resolve().parent
RUNS_DIR = HARNESS_DIR / "runs"
LOGS_DIR = HARNESS_DIR / "logs"
CLAUDE_PROJECTS = Path.home() / ".claude" / "projects"

TOKEN_FIELDS = [
    "input_tokens",
    "output_tokens",
    "cache_read_tokens",
    "cache_creation_tokens",
]


def _sum_jsonl_usage(filepath: Path) -> dict:
    """Sum token usage from a single JSONL session file."""
    usage = {k: 0 for k in TOKEN_FIELDS}
    with open(filepath) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue
            msg_usage = (
                msg.get("message", {}).get("usage", {})
                if isinstance(msg.get("message"), dict)
                else msg.get("usage", {})
            )
            if msg_usage:
                usage["input_tokens"] += msg_usage.get("input_tokens", 0)
                usage["output_tokens"] += msg_usage.get("output_tokens", 0)
                usage["cache_read_tokens"] += msg_usage.get("cache_read_input_tokens", 0)
                usage["cache_creation_tokens"] += msg_usage.get("cache_creation_input_tokens", 0)
    return usage


def get_subagent_usage_for_session(project_dir: Path, session_id: str) -> dict:
    """Get sub-agent token usage for a specific session."""
    usage = {k: 0 for k in TOKEN_FIELDS}
    subagents_dir = project_dir / session_id / "subagents"
    if not subagents_dir.is_dir():
        return usage
    for jsonl in subagents_dir.glob("*.jsonl"):
        sub = _sum_jsonl_usage(jsonl)
        for k in TOKEN_FIELDS:
            usage[k] += sub[k]
    return usage


def get_all_subagent_usage(project_dir: Path) -> dict:
    """Get total sub-agent token usage across ALL sessions in a project dir."""
    usage = {k: 0 for k in TOKEN_FIELDS}
    if not project_dir.is_dir():
        return usage
    for session_jsonl in project_dir.glob("*.jsonl"):
        session_id = session_jsonl.stem
        sub = get_subagent_usage_for_session(project_dir, session_id)
        for k in TOKEN_FIELDS:
            usage[k] += sub[k]
    return usage


def workspace_to_project_dir(workspace_path: Path) -> Path:
    """Convert a workspace path to its Claude projects directory.

    Claude Code encodes project paths by replacing / and _ with - and
    keeping the leading -.
    """
    encoded = str(workspace_path).replace("/", "-").replace("_", "-")
    return CLAUDE_PROJECTS / encoded


def find_run_dirs():
    """Yield (task_name, run_dir) for all benchmark runs."""
    if not RUNS_DIR.exists():
        return
    for task_dir in sorted(RUNS_DIR.iterdir()):
        if not task_dir.is_dir():
            continue
        for run_dir in sorted(task_dir.iterdir()):
            if not run_dir.is_dir():
                continue
            yield task_dir.name, run_dir


def correct_run(task_name, run_dir, apply=False):
    """Correct token counts for a single run. Returns a summary dict or None if no changes."""
    workspace = run_dir / "workspace"
    project_dir = workspace_to_project_dir(workspace)

    if not project_dir.exists():
        return None

    # Find result and log files
    results_dir = run_dir / "results"
    result_files = [
        f for f in results_dir.glob("*.json") if "experiment_tree" not in f.name
    ] if results_dir.exists() else []

    if not result_files:
        return None

    result_file = result_files[0]
    data = json.load(open(result_file))
    run_id = data.get("run_id", result_file.stem)

    # Find matching log file
    log_file = LOGS_DIR / task_name / f"{run_id}.json"
    log_data = json.load(open(log_file)) if log_file.exists() else None

    # Determine strategy: do we have session_ids in phase_breakdown?
    has_session_ids = False
    for stage in data.get("stages", []):
        for pb in stage.get("phase_breakdown", []):
            if pb.get("session_ids"):
                has_session_ids = True
                break

    total_sub_usage = get_all_subagent_usage(project_dir)
    if total_sub_usage["output_tokens"] == 0 and total_sub_usage["input_tokens"] == 0:
        return None  # No sub-agents in this run

    changes = []

    if has_session_ids:
        # Strategy 1: correct each phase individually
        for stage in data.get("stages", []):
            stage_delta = {k: 0 for k in TOKEN_FIELDS}
            for pb in stage.get("phase_breakdown", []):
                for sid in pb.get("session_ids", []):
                    sub = get_subagent_usage_for_session(project_dir, sid)
                    if sub["output_tokens"] == 0 and sub["input_tokens"] == 0:
                        continue
                    for k in TOKEN_FIELDS:
                        pb[k] = pb.get(k, 0) + sub[k]
                        stage_delta[k] += sub[k]
                pb["total_tokens"] = pb.get("input_tokens", 0) + pb.get("output_tokens", 0)

            if stage_delta["output_tokens"] > 0 or stage_delta["input_tokens"] > 0:
                for k in TOKEN_FIELDS:
                    stage[k] = stage.get(k, 0) + stage_delta[k]
                stage["total_tokens"] = stage["input_tokens"] + stage["output_tokens"]
                stage["token_cost"] = stage["total_tokens"]
                # Recompute effective_tokens
                cache_at_discount = stage.get("cache_read_tokens", 0) * 0.1
                non_cache = stage["input_tokens"] + stage["output_tokens"] + stage.get("cache_creation_tokens", 0)
                stage["effective_tokens"] = non_cache + cache_at_discount
                changes.append({
                    "stage": stage["stage_id"],
                    "delta": dict(stage_delta),
                    "method": "per-session",
                })
    else:
        # Strategy 2: distribute proportionally across stages
        # Compute each stage's share of parent output tokens
        stages = data.get("stages", [])
        parent_outputs = []
        for stage in stages:
            parent_outputs.append(stage.get("output_tokens", 0))
        total_parent_out = sum(parent_outputs)

        if total_parent_out == 0:
            # Fallback: distribute evenly
            weights = [1.0 / len(stages)] * len(stages) if stages else []
        else:
            weights = [p / total_parent_out for p in parent_outputs]

        for stage, weight in zip(stages, weights):
            stage_delta = {k: int(total_sub_usage[k] * weight) for k in TOKEN_FIELDS}
            if stage_delta["output_tokens"] == 0 and stage_delta["input_tokens"] == 0:
                continue
            for k in TOKEN_FIELDS:
                stage[k] = stage.get(k, 0) + stage_delta[k]
            stage["total_tokens"] = stage["input_tokens"] + stage["output_tokens"]
            stage["token_cost"] = stage["total_tokens"]
            cache_at_discount = stage.get("cache_read_tokens", 0) * 0.1
            non_cache = stage["input_tokens"] + stage["output_tokens"] + stage.get("cache_creation_tokens", 0)
            stage["effective_tokens"] = non_cache + cache_at_discount
            changes.append({
                "stage": stage["stage_id"],
                "delta": dict(stage_delta),
                "method": "proportional",
            })

    if not changes:
        return None

    # Apply same corrections to log_data
    if log_data:
        log_stages = {s["stage_id"]: s for s in log_data.get("stages", [])}
        for change in changes:
            ls = log_stages.get(change["stage"])
            if not ls:
                continue
            for k in TOKEN_FIELDS:
                ls[k] = ls.get(k, 0) + change["delta"][k]
            ls["total_tokens"] = ls["input_tokens"] + ls["output_tokens"]
            ls["token_cost"] = ls["total_tokens"]
            cache_at_discount = ls.get("cache_read_tokens", 0) * 0.1
            non_cache = ls["input_tokens"] + ls["output_tokens"] + ls.get("cache_creation_tokens", 0)
            ls["effective_tokens"] = non_cache + cache_at_discount

            # Also patch phase_breakdown in log if present
            if has_session_ids:
                result_stage = next(
                    (s for s in data["stages"] if s["stage_id"] == change["stage"]),
                    None,
                )
                if result_stage and ls.get("phase_breakdown"):
                    ls["phase_breakdown"] = result_stage["phase_breakdown"]

    if apply:
        with open(result_file, "w") as f:
            json.dump(data, f, indent=2)
            f.write("\n")
        if log_data and log_file.exists():
            with open(log_file, "w") as f:
                json.dump(log_data, f, indent=2)
                f.write("\n")

    return {
        "run_id": run_id,
        "task": task_name,
        "run_dir": str(run_dir.name),
        "method": changes[0]["method"] if changes else "none",
        "changes": changes,
        "files_patched": [str(result_file)]
        + ([str(log_file)] if log_data and log_file.exists() else []),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true", help="Write corrected files (default: dry-run)")
    args = parser.parse_args()

    mode = "APPLYING" if args.apply else "DRY RUN"
    print(f"=== Sub-agent token correction ({mode}) ===\n")

    corrected = []
    for task_name, run_dir in find_run_dirs():
        result = correct_run(task_name, run_dir, apply=args.apply)
        if result:
            corrected.append(result)

    if not corrected:
        print("No runs need correction.")
        return

    total_delta = {k: 0 for k in TOKEN_FIELDS}
    print(f"{'Run':<60} {'Method':<14} {'Stages':>6} {'+Output':>10} {'+CacheRead':>12}")
    print("-" * 105)
    for r in corrected:
        delta_out = sum(c["delta"]["output_tokens"] for c in r["changes"])
        delta_cr = sum(c["delta"]["cache_read_tokens"] for c in r["changes"])
        for c in r["changes"]:
            for k in TOKEN_FIELDS:
                total_delta[k] += c["delta"][k]
        n_stages = len(r["changes"])
        label = f"{r['task']}/{r['run_dir']}"
        print(f"{label:<60} {r['method']:<14} {n_stages:>6} {delta_out:>+10,} {delta_cr:>+12,}")

    print("-" * 105)
    print(f"{'TOTAL':<60} {'':14} {sum(len(r['changes']) for r in corrected):>6} "
          f"{total_delta['output_tokens']:>+10,} {total_delta['cache_read_tokens']:>+12,}")
    print(f"\nRuns corrected: {len(corrected)}")

    if not args.apply:
        print(f"\nThis was a dry run. Re-run with --apply to write changes.")
    else:
        print(f"\nAll files have been patched.")


if __name__ == "__main__":
    main()
