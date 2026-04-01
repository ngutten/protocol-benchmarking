#!/usr/bin/env python3
"""Re-run tests for completed experiment runs and update their log files.

Checks out each stage's git tag in the workspace, re-runs training, holdout,
regression, and perf tests using the current test suite, and patches the log
JSON with updated results.

Usage:
    # Re-run all runs for a specific task
    python3 rerun_tests.py --task pdesolver

    # Re-run a specific run
    python3 rerun_tests.py --task pdesolver --run direct_speed_20260325_005458

    # Filter by protocol
    python3 rerun_tests.py --task pdesolver --protocol direct_speed

    # Dry run — show what would change without writing
    python3 rerun_tests.py --task pdesolver --dry-run

    # Re-run all tasks
    python3 rerun_tests.py

    # Custom pytest timeout (default: 120s)
    python3 rerun_tests.py --task pdesolver --timeout 180
"""
import argparse
import json
import os
import subprocess
import sys
from dataclasses import asdict

# Add project root to path
sys.path.insert(0, os.path.dirname(__file__))
from harness.metrics import (
    collect_stage_metrics, count_code, run_pytest, run_perf_tests,
    StageMetrics, TestResult, PerfResult,
)


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOGS_DIR = os.path.join(BASE_DIR, "logs")
RUNS_DIR = os.path.join(BASE_DIR, "runs")
TASKS_DIR = os.path.join(BASE_DIR, "tasks")


def find_workspace(task, run_id):
    """Find the workspace directory for a given task and run_id."""
    runs_dir = os.path.join(RUNS_DIR, task)
    if not os.path.isdir(runs_dir):
        return None
    for d in os.listdir(runs_dir):
        ws = os.path.join(runs_dir, d, "workspace")
        if not os.path.isdir(ws):
            continue
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


def load_task_config(task):
    """Load engine_cmd and stage list from task.yaml."""
    import yaml
    task_yaml = os.path.join(TASKS_DIR, task, "task.yaml")
    if not os.path.exists(task_yaml):
        return None
    with open(task_yaml) as f:
        return yaml.safe_load(f)


def get_stage_list(task_cfg):
    """Get ordered list of numbered stage IDs from task config."""
    stages = []
    for i, s in enumerate(task_cfg.get("stages", []), 1):
        stages.append(f"{i:02d}_{s['id']}")
    return stages


def rerun_log(log_path, task, dry_run=False, timeout=120, verbose=False):
    """Re-run all tests for a single log file and update it.

    Returns a dict with summary info: {run_id, stages_updated, timeouts, warnings}.
    """
    with open(log_path) as f:
        data = json.load(f)

    run_id = data.get("run_id", "")
    if not run_id:
        print(f"  SKIP: no run_id in {log_path}")
        return None

    workspace = find_workspace(task, run_id)
    if not workspace:
        print(f"  SKIP: no workspace found for {run_id}")
        return None

    task_cfg = load_task_config(task)
    if not task_cfg:
        print(f"  SKIP: no task.yaml found for {task}")
        return None

    engine_cmd = task_cfg.get("engine_cmd", "python3 -c 'pass'")
    full_engine_cmd = f"cd {workspace} && {engine_cmd}"
    test_dir = os.path.join(TASKS_DIR, task, "tests")
    summary = {
        "run_id": run_id,
        "stages_updated": 0,
        "timeouts": [],
        "warnings": [],
        "zero_pass_stages": [],
    }

    # Save current HEAD so we can restore
    orig_ref = subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, text=True, cwd=workspace
    ).stdout.strip()

    changed = False
    previously_passed = set()  # accumulate passed holdout test names across stages

    try:
        for stage_data in data.get("stages", []):
            stage_id = stage_data.get("stage_id", "")
            tag = f"{run_id}/{stage_id}"

            # Check tag exists
            ret = subprocess.run(
                ["git", "rev-parse", tag], capture_output=True, text=True, cwd=workspace
            )
            if ret.returncode != 0:
                print(f"    SKIP stage {stage_id}: tag '{tag}' not found")
                summary["warnings"].append(f"{stage_id}: tag not found")
                continue

            # Force-clean and checkout the tag
            # __pycache__ and other generated files can block checkout
            subprocess.run(
                ["git", "clean", "-fd", "--quiet"], capture_output=True, cwd=workspace
            )
            checkout_result = subprocess.run(
                ["git", "checkout", "-f", tag, "--quiet"],
                capture_output=True, text=True, cwd=workspace
            )
            if checkout_result.returncode != 0:
                print(f"    SKIP stage {stage_id}: checkout failed: {checkout_result.stderr.strip()}")
                summary["warnings"].append(f"{stage_id}: checkout failed")
                continue
            # Clean again after checkout to remove any generated artifacts
            subprocess.run(
                ["git", "clean", "-fd", "--quiet"], capture_output=True, cwd=workspace
            )

            # Determine previous stages for regression tests
            # Use actual stage_ids from the log (which may be unnumbered)
            # rather than the numbered list from task.yaml
            previous_stages = []
            for sd in data["stages"]:
                if sd["stage_id"] == stage_id:
                    break
                previous_stages.append(sd["stage_id"])

            # Collect fresh metrics
            print(f"    Running tests for {stage_id}...", end="", flush=True)
            metrics = collect_stage_metrics(
                stage_id=stage_id,
                protocol=stage_data.get("protocol", "unknown"),
                project_dir=workspace,
                test_dir=test_dir,
                engine_cmd=full_engine_cmd,
                previous_stages=previous_stages,
                timeout=timeout,
                previously_passed=previously_passed,
            )

            # Check for timeout indicators (run_pytest returns empty on timeout)
            # We detect this by checking if test counts dropped to 0 unexpectedly
            # Actually, let's check by running a quick validation
            timed_out = False
            if metrics.training_tests_total == 0 and stage_data.get("training_tests_total", 0) > 0:
                # Training tests disappeared — possible timeout or import error
                # Re-check: could be legitimate if tests were removed
                tp = os.path.join(test_dir, "training")
                stage_prefix = stage_id.split("_")[0] if "_" in stage_id else ""
                import re
                has_test_files = False
                if os.path.isdir(tp):
                    for f in os.listdir(tp):
                        if (stage_id in f or (stage_prefix and re.match(rf"test_{stage_prefix}_", f))) and f.endswith(".py"):
                            has_test_files = True
                            break
                if has_test_files:
                    summary["warnings"].append(f"{stage_id}: training tests exist but got 0 results (possible timeout)")

            # Build comparison for reporting
            fields_to_update = [
                "training_tests_total", "training_tests_passed",
                "holdout_tests_total", "holdout_tests_passed",
                "regression_tests_total", "regression_tests_failed",
                "perf_tests_total", "perf_tests_passed",
                "code_lines", "code_bytes",
            ]

            stage_changed = False
            changes = []
            metrics_dict = metrics.to_dict()

            for field in fields_to_update:
                old_val = stage_data.get(field, 0)
                new_val = metrics_dict.get(field, 0)
                if old_val != new_val:
                    changes.append(f"{field}: {old_val} -> {new_val}")
                    stage_changed = True

            # Always update test_results and perf_results with fresh data
            new_test_results = metrics_dict.get("test_results", [])
            new_perf_results = metrics_dict.get("perf_results", [])

            # Also update computed fields
            computed_fields = [
                "training_accuracy", "holdout_accuracy", "regression_rate",
                "perf_mean_duration",
            ]

            if stage_changed or True:  # Always update test_results
                for field in fields_to_update:
                    stage_data[field] = metrics_dict.get(field, 0)
                for field in computed_fields:
                    stage_data[field] = metrics_dict.get(field)
                stage_data["test_results"] = new_test_results
                stage_data["perf_results"] = new_perf_results
                changed = True
                summary["stages_updated"] += 1

            # Detect zero pass rate
            if metrics.holdout_tests_total > 0 and metrics.holdout_tests_passed == 0:
                summary["zero_pass_stages"].append(stage_id)

            # Report
            if changes:
                print(f" CHANGED")
                for c in changes:
                    print(f"      {c}")
            else:
                print(f" unchanged (train={metrics.training_tests_passed}/{metrics.training_tests_total}, "
                      f"holdout={metrics.holdout_tests_passed}/{metrics.holdout_tests_total})")

            if verbose:
                print(f"      regression={metrics.regression_tests_failed}/{metrics.regression_tests_total} failures, "
                      f"perf={metrics.perf_tests_passed}/{metrics.perf_tests_total}, "
                      f"code={metrics.code_lines} lines")

            # Accumulate passed holdout tests for regression tracking in later stages
            for r in metrics.test_results:
                if r.pool == "holdout" and r.passed:
                    previously_passed.add(r.name)

    finally:
        # Restore original HEAD
        subprocess.run(
            ["git", "clean", "-fd", "--quiet"], capture_output=True, cwd=workspace
        )
        subprocess.run(
            ["git", "checkout", "-f", orig_ref, "--quiet"], capture_output=True, cwd=workspace
        )

    if changed and not dry_run:
        with open(log_path, "w") as f:
            json.dump(data, f, indent=2, default=str)
        print(f"    UPDATED {os.path.basename(log_path)}")
    elif changed and dry_run:
        print(f"    [DRY RUN] would update {os.path.basename(log_path)}")

    return summary


def check_failed_runs(log_path, task):
    """Check if a run should be marked as 'failed' based on test results.

    Returns list of stages with 0% holdout pass rate.
    """
    with open(log_path) as f:
        data = json.load(f)

    zero_stages = []
    for stage in data.get("stages", []):
        total = stage.get("holdout_tests_total", 0)
        passed = stage.get("holdout_tests_passed", 0)
        if total > 0 and passed == 0:
            zero_stages.append({
                "stage_id": stage["stage_id"],
                "holdout_total": total,
                "training_passed": stage.get("training_tests_passed", 0),
                "training_total": stage.get("training_tests_total", 0),
            })
    return zero_stages


def recompute_regressions_for_log(log_path, dry_run=False):
    """Recompute regression counts from existing test_results in a log file.

    Uses the new definition: a regression is a test that passed in a prior stage
    but fails now. No git checkouts or pytest runs needed.

    Returns number of stages with changed regression counts.
    """
    with open(log_path) as f:
        data = json.load(f)

    previously_passed = set()
    changed_count = 0

    for stage_data in data.get("stages", []):
        stage_id = stage_data.get("stage_id", "")
        test_results = stage_data.get("test_results", [])

        # Recount regressions from stored test_results
        reg_total = 0
        reg_failed = 0
        for r in test_results:
            if r.get("pool") == "regression":
                reg_total += 1
                if not r.get("passed", False):
                    if r.get("name", "") in previously_passed:
                        reg_failed += 1

        old_total = stage_data.get("regression_tests_total", 0)
        old_failed = stage_data.get("regression_tests_failed", 0)

        if old_total != reg_total or old_failed != reg_failed:
            print(f"    {stage_id}: regression_tests_failed {old_failed} -> {reg_failed} "
                  f"(total {old_total} -> {reg_total})")
            stage_data["regression_tests_total"] = reg_total
            stage_data["regression_tests_failed"] = reg_failed
            stage_data["regression_rate"] = reg_failed / reg_total if reg_total else 0.0
            changed_count += 1
        else:
            print(f"    {stage_id}: unchanged ({reg_failed}/{reg_total})")

        # Accumulate passed holdout tests for later stages
        for r in test_results:
            if r.get("pool") == "holdout" and r.get("passed", False):
                previously_passed.add(r.get("name", ""))

    if changed_count > 0 and not dry_run:
        with open(log_path, "w") as f:
            json.dump(data, f, indent=2, default=str)
        print(f"    UPDATED {os.path.basename(log_path)}")
    elif changed_count > 0 and dry_run:
        print(f"    [DRY RUN] would update {os.path.basename(log_path)}")

    return changed_count


def main():
    parser = argparse.ArgumentParser(
        description="Re-run tests for completed experiment runs and update log files."
    )
    parser.add_argument("--task", "-t", help="Task name (e.g. pdesolver). Omit for all tasks.")
    parser.add_argument("--run", "-r", help="Specific run_id to process.")
    parser.add_argument("--protocol", "-p", help="Filter by protocol name (prefix match).")
    parser.add_argument("--dry-run", "-n", action="store_true", help="Show changes without writing.")
    parser.add_argument("--timeout", type=int, default=300, help="Pytest timeout in seconds (default: 300).")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show detailed per-stage output.")
    parser.add_argument("--recompute-regressions", action="store_true",
                        help="Only recompute regression counts from existing test_results (no re-running).")
    args = parser.parse_args()

    if args.dry_run:
        print("DRY RUN — no files will be modified\n")

    # Determine which tasks to process
    if args.task:
        tasks = [args.task]
    else:
        tasks = sorted(d for d in os.listdir(LOGS_DIR)
                       if os.path.isdir(os.path.join(LOGS_DIR, d)))

    all_summaries = []
    all_zero_pass = []

    for task in tasks:
        task_log_dir = os.path.join(LOGS_DIR, task)
        if not os.path.isdir(task_log_dir):
            print(f"No logs directory for task '{task}'")
            continue

        log_files = sorted(f for f in os.listdir(task_log_dir)
                           if f.endswith(".json") and f != "experiment_tree.json")

        # Filter by run_id
        if args.run:
            log_files = [f for f in log_files if args.run in f]

        # Filter by protocol
        if args.protocol:
            log_files = [f for f in log_files if f.startswith(args.protocol)]

        if not log_files:
            print(f"No matching log files for task '{task}'")
            continue

        print(f"\n{'='*60}")
        print(f"TASK: {task} ({len(log_files)} runs)")
        print(f"{'='*60}")

        for fname in log_files:
            log_path = os.path.join(task_log_dir, fname)
            run_id = fname.replace(".json", "")
            print(f"\n  {run_id}:")

            if args.recompute_regressions:
                recompute_regressions_for_log(log_path, dry_run=args.dry_run)
                continue

            summary = rerun_log(log_path, task, dry_run=args.dry_run,
                                timeout=args.timeout, verbose=args.verbose)
            if summary:
                all_summaries.append((task, summary))

            # Check for failed runs (0% holdout)
            zero_stages = check_failed_runs(log_path, task)
            if zero_stages:
                for zs in zero_stages:
                    all_zero_pass.append((task, run_id, zs))

    # Print summary
    print(f"\n{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}")

    total_updated = sum(s["stages_updated"] for _, s in all_summaries)
    print(f"\nRuns processed: {len(all_summaries)}")
    print(f"Stages updated: {total_updated}")

    # Report timeouts
    all_timeouts = [(t, s["run_id"], to) for t, s in all_summaries for to in s.get("timeouts", [])]
    if all_timeouts:
        print(f"\nTIMEOUTS ({len(all_timeouts)}):")
        for task, run_id, timeout_info in all_timeouts:
            print(f"  {task}/{run_id}: {timeout_info}")

    # Report warnings
    all_warnings = [(t, s["run_id"], w) for t, s in all_summaries for w in s.get("warnings", [])]
    if all_warnings:
        print(f"\nWARNINGS ({len(all_warnings)}):")
        for task, run_id, warning in all_warnings:
            print(f"  {task}/{run_id}: {warning}")

    # Report zero pass rate stages (potential failed runs)
    if all_zero_pass:
        print(f"\nZERO HOLDOUT PASS RATE ({len(all_zero_pass)} stages):")
        for task, run_id, zs in all_zero_pass:
            print(f"  {task}/{run_id} stage {zs['stage_id']}: "
                  f"holdout 0/{zs['holdout_total']}, "
                  f"training {zs['training_passed']}/{zs['training_total']}")
    else:
        print("\nNo stages with 0% holdout pass rate.")


if __name__ == "__main__":
    main()
