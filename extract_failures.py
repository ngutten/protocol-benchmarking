#!/usr/bin/env python3
"""Extract failure messages for specific never-passed tests from JSON logs."""

import json
import os
import glob
from collections import defaultdict

TASKS_AND_TESTS = {
    "cellautomata": [
        "test_auto_stepping_advances_simulation",
    ],
    "maze": [
        "test_corridor_shows_depth",
        "test_three_cell_visibility",
        "test_water_uses_water_texture",
    ],
    "minidb": [
        "test_flatten_with_group_by",
    ],
    "roguelike_condensed": [
        "test_mobility_order",
        "test_status_effect_message",
        "test_weight_tracking",
        "test_descend_stairs",
        "test_leaping_strike",
        "test_magic_missile_costs_mp",
        "test_tile_memory_is_level_specific",
        "test_player_death_archives_save",
    ],
}

LOG_BASE = "/home/claude/benchmarks/tests/logs"

def extract_failures():
    results = defaultdict(list)  # test_name -> list of (log_file, failure_info)

    for task, test_names in TASKS_AND_TESTS.items():
        log_dir = os.path.join(LOG_BASE, task)
        if not os.path.exists(log_dir):
            print(f"WARNING: Log dir not found: {log_dir}")
            continue

        log_files = glob.glob(os.path.join(log_dir, "*.json"))
        print(f"\n{'='*60}")
        print(f"Task: {task} ({len(log_files)} log files)")
        print(f"{'='*60}")

        # Collect failures per test
        test_failures = defaultdict(list)

        for log_file in log_files:
            try:
                with open(log_file) as f:
                    data = json.load(f)
            except Exception as e:
                print(f"  ERROR reading {log_file}: {e}")
                continue

            # Search for test results - handle different JSON structures
            test_results = []

            # Try different structures
            if isinstance(data, dict):
                # Look for stages
                if "stages" in data:
                    for stage in data["stages"]:
                        if "test_results" in stage:
                            test_results.extend(stage["test_results"])
                        if "tests" in stage:
                            test_results.extend(stage["tests"])
                # Direct test_results
                if "test_results" in data:
                    test_results.extend(data["test_results"])
                if "tests" in data:
                    test_results.extend(data["tests"])
                # results key
                if "results" in data:
                    r = data["results"]
                    if isinstance(r, list):
                        test_results.extend(r)
                    elif isinstance(r, dict) and "test_results" in r:
                        test_results.extend(r["test_results"])

            for tr in test_results:
                if not isinstance(tr, dict):
                    continue
                test_id = tr.get("test_id", tr.get("nodeid", tr.get("name", "")))

                # Check if this matches any of our target tests
                for test_name in test_names:
                    if test_name in test_id:
                        outcome = tr.get("outcome", tr.get("status", "unknown"))
                        if outcome in ("failed", "error", "FAILED", "ERROR"):
                            longrepr = tr.get("longrepr", tr.get("message", tr.get("error", tr.get("failure", ""))))
                            test_failures[test_name].append({
                                "log_file": os.path.basename(log_file),
                                "test_id": test_id,
                                "outcome": outcome,
                                "longrepr": longrepr,
                            })

        for test_name in test_names:
            failures = test_failures[test_name]
            print(f"\n--- {test_name} ({len(failures)} failures found) ---")
            if not failures:
                print("  No failure records found in logs!")
                # Debug: check what keys are in the first log file
                if log_files:
                    try:
                        with open(log_files[0]) as f:
                            d = json.load(f)
                        print(f"  Debug - top-level keys in first log: {list(d.keys()) if isinstance(d, dict) else type(d)}")
                        if isinstance(d, dict) and "stages" in d:
                            for i, stage in enumerate(d["stages"][:2]):
                                print(f"    Stage {i} keys: {list(stage.keys()) if isinstance(stage, dict) else type(stage)}")
                                if isinstance(stage, dict):
                                    for k, v in stage.items():
                                        if isinstance(v, list) and v:
                                            print(f"      {k}[0] keys: {list(v[0].keys()) if isinstance(v[0], dict) else type(v[0])}")
                    except:
                        pass
            else:
                # Show unique failure messages (deduplicated)
                seen_msgs = set()
                for f_info in failures[:5]:  # max 5 examples
                    msg_key = str(f_info["longrepr"])[:200]
                    if msg_key not in seen_msgs:
                        seen_msgs.add(msg_key)
                        print(f"\n  File: {f_info['log_file']}")
                        print(f"  Test ID: {f_info['test_id']}")
                        longrepr = f_info["longrepr"]
                        if isinstance(longrepr, str):
                            # Print last 1500 chars (most relevant part)
                            if len(longrepr) > 2000:
                                print(f"  Failure (truncated to last 2000 chars):\n{longrepr[-2000:]}")
                            else:
                                print(f"  Failure:\n{longrepr}")
                        elif isinstance(longrepr, dict):
                            print(f"  Failure (dict): {json.dumps(longrepr, indent=2)[:2000]}")
                        elif isinstance(longrepr, list):
                            print(f"  Failure (list): {json.dumps(longrepr, indent=2)[:2000]}")
                        else:
                            print(f"  Failure: {longrepr}")

if __name__ == "__main__":
    extract_failures()
