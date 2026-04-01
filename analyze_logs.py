#!/usr/bin/env python3
"""Analyze all run log files to find tests that never pass or fail very frequently."""

import json
import os
from collections import defaultdict
from pathlib import Path

LOGS_BASE = Path("/home/claude/benchmarks/tests/logs")
TASKS = [
    "cellautomata",
    "maze",
    "minidb",
    "pdesolver",
    "plotcurve",
    "roguelike_condensed",
]

# Structure: task -> test_id -> {"passes": int, "runs": int, "name": str}
test_stats = defaultdict(lambda: defaultdict(lambda: {"passes": 0, "runs": 0, "name": ""}))

# Structure: task -> perf_test_name -> {"passes": int, "runs": int, "zero_duration": int}
perf_stats = defaultdict(lambda: defaultdict(lambda: {"passes": 0, "runs": 0, "zero_duration": 0}))

file_counts = {}

for task in TASKS:
    task_dir = LOGS_BASE / task
    if not task_dir.exists():
        print(f"  [SKIP] {task} - directory not found")
        continue

    json_files = list(task_dir.glob("*.json"))
    file_counts[task] = len(json_files)

    for json_file in json_files:
        try:
            with open(json_file) as f:
                data = json.load(f)
        except Exception as e:
            print(f"  [ERROR] {json_file}: {e}")
            continue

        stages = data.get("stages", [])
        for stage in stages:
            # Process test_results
            for tr in stage.get("test_results", []):
                test_id = tr.get("name", "")
                if not test_id:
                    continue
                passed = tr.get("passed", False)
                test_stats[task][test_id]["runs"] += 1
                if passed:
                    test_stats[task][test_id]["passes"] += 1
                test_stats[task][test_id]["name"] = test_id

            # Process perf_results
            for pr in stage.get("perf_results", []):
                pname = pr.get("name", "")
                if not pname:
                    continue
                passed = pr.get("passed", False)
                duration = pr.get("duration_seconds", 0.0)
                perf_stats[task][pname]["runs"] += 1
                if passed:
                    perf_stats[task][pname]["passes"] += 1
                if duration == 0.0:
                    perf_stats[task][pname]["zero_duration"] += 1

print("=" * 80)
print("LOG FILE ANALYSIS: Test Pass Rate Report")
print("=" * 80)

# --------------------------------------------------------------------------
# Per-task summary
# --------------------------------------------------------------------------
print("\n## PER-TASK SUMMARY\n")
print(f"{'Task':<25} {'Files':>6} {'Tests':>7} {'Never Passed':>13} {'<20% Pass Rate':>15}")
print("-" * 70)

all_never_passed = []
all_low_pass = []

for task in TASKS:
    if task not in test_stats:
        print(f"{task:<25} {'N/A':>6}")
        continue

    n_files = file_counts.get(task, 0)
    tests = test_stats[task]
    n_tests = len(tests)

    never_passed = [(tid, s) for tid, s in tests.items() if s["passes"] == 0]
    low_pass = [
        (tid, s) for tid, s in tests.items()
        if s["runs"] > 0 and (s["passes"] / s["runs"]) < 0.20 and s["passes"] > 0
    ]

    print(f"{task:<25} {n_files:>6} {n_tests:>7} {len(never_passed):>13} {len(low_pass):>15}")

    all_never_passed.append((task, never_passed))
    all_low_pass.append((task, low_pass))

# --------------------------------------------------------------------------
# Tests that NEVER passed
# --------------------------------------------------------------------------
print("\n\n## TESTS THAT NEVER PASSED (0 passes across all runs)\n")

for task, tests in all_never_passed:
    if not tests:
        print(f"[{task}] - None found\n")
        continue
    print(f"[{task}] - {len(tests)} test(s):\n")
    # Sort by number of runs descending (most-attempted first)
    tests_sorted = sorted(tests, key=lambda x: -x[1]["runs"])
    for tid, s in tests_sorted:
        short_name = tid.split("::")[-1] if "::" in tid else tid
        module_path = "::".join(tid.split("::")[:-1]) if "::" in tid else ""
        # Shorten path: keep from "tests/" onward
        if "tests/" in module_path:
            module_path = "tests/" + module_path.split("tests/", 1)[1]
        print(f"  NEVER PASSED  runs={s['runs']:>3}  {module_path}::{short_name}")
    print()

# --------------------------------------------------------------------------
# Tests that pass <20% of the time (but at least once)
# --------------------------------------------------------------------------
print("\n## TESTS WITH PASS RATE < 20% (but not zero)\n")

for task, tests in all_low_pass:
    if not tests:
        print(f"[{task}] - None found\n")
        continue
    print(f"[{task}] - {len(tests)} test(s):\n")
    tests_sorted = sorted(tests, key=lambda x: x[1]["passes"] / x[1]["runs"])
    for tid, s in tests_sorted:
        rate = s["passes"] / s["runs"] * 100
        short_name = tid.split("::")[-1] if "::" in tid else tid
        module_path = "::".join(tid.split("::")[:-1]) if "::" in tid else ""
        if "tests/" in module_path:
            module_path = "tests/" + module_path.split("tests/", 1)[1]
        print(f"  {rate:5.1f}%  passes={s['passes']}/{s['runs']}  {module_path}::{short_name}")
    print()

# --------------------------------------------------------------------------
# Perf test issues
# --------------------------------------------------------------------------
print("\n## PERF TEST ISSUES (failed or duration=0.0)\n")

any_perf_issue = False
for task in TASKS:
    if task not in perf_stats:
        continue

    issues = []
    for pname, s in perf_stats[task].items():
        if s["runs"] == 0:
            continue
        fail_rate = (s["runs"] - s["passes"]) / s["runs"]
        zero_rate = s["zero_duration"] / s["runs"]
        if fail_rate > 0 or zero_rate > 0:
            issues.append((pname, s, fail_rate, zero_rate))

    if issues:
        any_perf_issue = True
        print(f"[{task}]:\n")
        issues_sorted = sorted(issues, key=lambda x: -x[2])
        for pname, s, fail_rate, zero_rate in issues_sorted:
            short = pname.split("::")[-1] if "::" in pname else pname
            module = "::".join(pname.split("::")[:-1]) if "::" in pname else ""
            if "tests/" in module:
                module = "tests/" + module.split("tests/", 1)[1]
            flags = []
            if fail_rate > 0:
                flags.append(f"FAILED {int(fail_rate*100)}% of runs ({s['runs']-s['passes']}/{s['runs']})")
            if zero_rate > 0:
                flags.append(f"duration=0.0 in {int(zero_rate*100)}% ({s['zero_duration']}/{s['runs']})")
            print(f"  {', '.join(flags)}")
            print(f"    {module}::{short}")
        print()

if not any_perf_issue:
    print("  No perf issues found.\n")

# --------------------------------------------------------------------------
# Aggregate stats
# --------------------------------------------------------------------------
print("\n## AGGREGATE STATISTICS\n")
total_tests = sum(len(v) for v in test_stats.values())
total_never = sum(len([t for t in v.values() if t["passes"] == 0]) for v in test_stats.values())
total_low = sum(
    len([t for t in v.values() if t["runs"] > 0 and t["passes"] > 0 and t["passes"]/t["runs"] < 0.20])
    for v in test_stats.values()
)
total_files = sum(file_counts.values())
print(f"Total log files analyzed : {total_files}")
print(f"Total unique tests tracked: {total_tests}")
print(f"Tests that NEVER passed  : {total_never}")
print(f"Tests with <20% pass rate: {total_low}")
print(f"Tests needing attention  : {total_never + total_low}")
