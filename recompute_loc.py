#!/usr/bin/env python3
"""Recompute code_lines and code_bytes in existing log files using git tag snapshots.

For each stage in each log, checks out the corresponding git tag in the
workspace, runs the updated count_code(), and patches the log JSON.
"""
import json
import os
import subprocess
import sys

# Add harness to path
sys.path.insert(0, os.path.dirname(__file__))
from harness.metrics import count_code


def find_workspace(task, run_id):
    """Find the workspace directory for a given task and run_id."""
    runs_dir = os.path.join(os.path.dirname(__file__), "runs", task)
    if not os.path.isdir(runs_dir):
        return None
    # run dirs are named like protocol_timestamp (e.g. direct_no_tests_1773863643)
    # run_id is like direct_no_tests_20260318_125403
    for d in os.listdir(runs_dir):
        ws = os.path.join(runs_dir, d, "workspace")
        if not os.path.isdir(ws):
            continue
        # Check if this workspace has tags matching the run_id
        try:
            tags = subprocess.run(
                ["git", "tag"], capture_output=True, text=True, cwd=ws
            ).stdout.strip().splitlines()
        except Exception:
            continue
        for tag in tags:
            if tag.startswith(run_id + "/"):
                return ws
    return None


def recompute_log(log_path, task, dry_run=False):
    """Recompute code_lines/code_bytes for all stages in a log file."""
    with open(log_path) as f:
        data = json.load(f)

    run_id = data.get("run_id", "")
    if not run_id:
        print(f"  SKIP: no run_id in {log_path}")
        return False

    workspace = find_workspace(task, run_id)
    if not workspace:
        print(f"  SKIP: no workspace found for {run_id}")
        return False

    changed = False
    # Save current HEAD so we can restore
    orig_ref = subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, text=True, cwd=workspace
    ).stdout.strip()

    try:
        for stage in data.get("stages", []):
            stage_id = stage.get("stage_id", "")
            tag = f"{run_id}/{stage_id}"

            # Check tag exists
            ret = subprocess.run(
                ["git", "rev-parse", tag], capture_output=True, text=True, cwd=workspace
            )
            if ret.returncode != 0:
                print(f"  SKIP stage {stage_id}: tag '{tag}' not found")
                continue

            # Checkout the tag
            subprocess.run(
                ["git", "checkout", tag, "--quiet"], capture_output=True, cwd=workspace
            )

            # Recount
            new_lines, new_bytes = count_code(workspace)
            old_lines = stage.get("code_lines", 0)
            old_bytes = stage.get("code_bytes", 0)

            if new_lines != old_lines or new_bytes != old_bytes:
                print(f"  {stage_id}: {old_lines} -> {new_lines} lines, {old_bytes} -> {new_bytes} bytes")
                stage["code_lines"] = new_lines
                stage["code_bytes"] = new_bytes
                changed = True
            else:
                print(f"  {stage_id}: unchanged ({new_lines} lines)")
    finally:
        # Restore original HEAD
        subprocess.run(
            ["git", "checkout", orig_ref, "--quiet"], capture_output=True, cwd=workspace
        )

    if changed and not dry_run:
        with open(log_path, "w") as f:
            json.dump(data, f, indent=2)
        print(f"  UPDATED {log_path}")

    return changed


def main():
    dry_run = "--dry-run" in sys.argv
    if dry_run:
        print("DRY RUN — no files will be modified\n")

    logs_dir = os.path.join(os.path.dirname(__file__), "logs")
    for task in sorted(os.listdir(logs_dir)):
        task_dir = os.path.join(logs_dir, task)
        if not os.path.isdir(task_dir):
            continue
        for fname in sorted(os.listdir(task_dir)):
            if not fname.endswith(".json") or fname == "experiment_tree.json":
                continue
            log_path = os.path.join(task_dir, fname)
            print(f"\n{task}/{fname} (run_id from file):")
            recompute_log(log_path, task, dry_run=dry_run)


if __name__ == "__main__":
    main()
