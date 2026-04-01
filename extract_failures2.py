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
    for task, test_names in TASKS_AND_TESTS.items():
        log_dir = os.path.join(LOG_BASE, task)
        if not os.path.exists(log_dir):
            print(f"WARNING: Log dir not found: {log_dir}")
            continue

        log_files = sorted(glob.glob(os.path.join(log_dir, "*.json")))
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

            if not isinstance(data, dict) or "stages" not in data:
                continue

            for stage in data["stages"]:
                if not isinstance(stage, dict):
                    continue
                test_results = stage.get("test_results", [])
                for tr in test_results:
                    if not isinstance(tr, dict):
                        continue
                    name = tr.get("name", "")
                    passed = tr.get("passed", True)

                    for test_name in test_names:
                        if test_name in name and not passed:
                            error = tr.get("error", tr.get("longrepr", tr.get("message", "")))
                            test_failures[test_name].append({
                                "log_file": os.path.basename(log_file),
                                "name": name,
                                "error": error,
                                "stage_id": stage.get("stage_id", "?"),
                            })

        for test_name in test_names:
            failures = test_failures[test_name]
            print(f"\n--- {test_name} ({len(failures)} failure records) ---")
            if not failures:
                # Check if any test with this name exists at all (even passing)
                found_any = False
                for log_file in log_files[:3]:
                    try:
                        with open(log_file) as f:
                            data = json.load(f)
                        for stage in data.get("stages", []):
                            for tr in stage.get("test_results", []):
                                if test_name in tr.get("name", ""):
                                    found_any = True
                                    print(f"  Found (passed={tr.get('passed')}) in {os.path.basename(log_file)}: {tr.get('name')}")
                    except:
                        pass
                if not found_any:
                    print(f"  NOT FOUND in any test results (first 3 logs)")
            else:
                seen_errors = set()
                for f_info in failures:
                    err_key = str(f_info["error"])[:300]
                    if err_key not in seen_errors:
                        seen_errors.add(err_key)
                        print(f"\n  File: {f_info['log_file']} (stage: {f_info['stage_id']})")
                        print(f"  Name: {f_info['name']}")
                        err = f_info["error"]
                        if isinstance(err, str):
                            if len(err) > 3000:
                                print(f"  Error (last 3000 chars):\n{err[-3000:]}")
                            else:
                                print(f"  Error:\n{err}")
                        elif err:
                            print(f"  Error: {json.dumps(err, indent=2)[:3000]}")
                        else:
                            print(f"  Error: (no error text recorded)")


if __name__ == "__main__":
    extract_failures()
