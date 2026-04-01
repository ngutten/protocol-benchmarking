#!/usr/bin/env python3
"""Extract failure messages for TestMazeGenerationQuality::test_multiple_regenerations_differ"""
import json
import os
import glob

TARGET_TEST = "test_multiple_regenerations_differ"
TARGET_CLASS = "TestMazeGenerationQuality"

log_dir = "/home/claude/benchmarks/tests/logs/maze"
log_files = sorted(glob.glob(os.path.join(log_dir, "*.json")))

print(f"Found {len(log_files)} log files\n")

total_runs = 0
failures = []
passes = 0

for log_path in log_files:
    with open(log_path) as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError as e:
            print(f"  ERROR reading {log_path}: {e}")
            continue

    # Traverse all test results in the log
    def find_tests(obj, path=""):
        results = []
        if isinstance(obj, dict):
            # Check if this is a test result node
            if "nodeid" in obj or "test_id" in obj:
                nid = obj.get("nodeid", obj.get("test_id", ""))
                if TARGET_TEST in nid:
                    results.append(obj)
            # Also look in common result list fields
            for key in ("tests", "results", "test_results", "items"):
                if key in obj:
                    results.extend(find_tests(obj[key], path + f".{key}"))
            for k, v in obj.items():
                if isinstance(v, (dict, list)) and k not in ("tests", "results", "test_results", "items"):
                    results.extend(find_tests(v, path + f".{k}"))
        elif isinstance(obj, list):
            for item in obj:
                results.extend(find_tests(item, path))
        return results

    matches = find_tests(data)
    for match in matches:
        total_runs += 1
        outcome = match.get("outcome", match.get("status", match.get("result", "unknown")))
        if outcome in ("failed", "error", "FAILED", "ERROR"):
            msg = match.get("longrepr", match.get("message", match.get("failure", match.get("error", ""))))
            if isinstance(msg, dict):
                msg = json.dumps(msg)
            failures.append({
                "file": os.path.basename(log_path),
                "outcome": outcome,
                "message": str(msg)[:2000],
            })
        elif outcome in ("passed", "PASSED"):
            passes += 1

print(f"Total runs of {TARGET_TEST}: {total_runs}")
print(f"  Passed: {passes}")
print(f"  Failed: {len(failures)}")
print()

for i, f in enumerate(failures):
    print(f"=== Failure #{i+1} from {f['file']} ===")
    print(f"Outcome: {f['outcome']}")
    print(f"Message:\n{f['message']}")
    print()
