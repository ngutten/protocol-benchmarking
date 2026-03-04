#!/usr/bin/env python3
"""CLI entry point for running benchmark experiments."""
import argparse
import sys
import time
import os

# Add parent to path so we can import harness as a package
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from harness.experiment import Experiment, setup_run_directory
from harness.protocols import ALL_PROTOCOLS
from harness.claude_runner import run_headless, run_interactive


def main():
    parser = argparse.ArgumentParser(description="MiniDB Benchmark Harness")
    parser.add_argument("--task-dir", required=True, help="Path to task directory")
    parser.add_argument("--protocol", required=True, choices=list(ALL_PROTOCOLS.keys()))
    parser.add_argument("--work-dir", help="Working directory (default: auto-created under runs/)")
    parser.add_argument("--log-dir", help="Directory for log output (default: auto-created under runs/)")
    parser.add_argument("--engine-cmd", default="python3 minidb.py", help="Command to start the engine")
    parser.add_argument("--stages", nargs="*", help="Specific stages to run (default: all)")
    parser.add_argument("--mode", choices=["headless", "interactive", "manual"],
                        default=None, help="Run mode (default: auto from protocol)")
    parser.add_argument("--timeout", type=int, default=None,
                        help="Timeout in seconds per stage for headless mode")
    parser.add_argument("--run-id", help="Custom run ID (default: auto-generated)")
    parser.add_argument("--model", help="Override model from protocol (e.g. claude-sonnet-4-6)")
    args = parser.parse_args()

    protocol = ALL_PROTOCOLS[args.protocol]

    # Allow CLI model override
    if args.model:
        protocol.model = args.model

    # Determine run mode
    if args.mode:
        mode = args.mode
    elif protocol.human_supervised:
        mode = "interactive"
    else:
        mode = "headless"

    # Set up run directory if work-dir/log-dir not explicitly provided
    if not args.work_dir or not args.log_dir:
        run_id = args.run_id or f"{args.protocol}_{int(time.time())}"
        dirs = setup_run_directory(run_id, args.task_dir, protocol)
        work_dir = args.work_dir or dirs["workspace"]
        log_dir = args.log_dir or dirs["results"]
    else:
        work_dir = args.work_dir
        log_dir = args.log_dir

    exp = Experiment(
        task_dir=args.task_dir,
        protocol_name=args.protocol,
        work_dir=work_dir,
        log_dir=log_dir,
        engine_cmd=args.engine_cmd,
    )
    exp.setup()

    stages = args.stages or exp.stages

    for stage_id in stages:
        exp.prepare_stage(stage_id)
        prompt = exp.build_stage_prompt(stage_id)

        if mode == "headless":
            print(f"\nRunning headless Claude ({protocol.model}) for stage {stage_id}...")
            result = run_headless(work_dir, prompt, protocol=protocol, timeout=args.timeout)
            human_time = result["wall_time_seconds"]
            token_data = {
                "input_tokens": result["input_tokens"],
                "output_tokens": result["output_tokens"],
                "total_tokens": result["total_tokens"],
                "cache_read_tokens": result["cache_read_tokens"],
                "cache_creation_tokens": result["cache_creation_tokens"],
            }
            if result["is_error"]:
                print(f"  WARNING: Claude returned error: {result['result'][:200]}")

        elif mode == "interactive":
            result = run_interactive(work_dir, prompt, protocol=protocol)
            human_time = result["wall_time_seconds"]
            token_data = {
                "input_tokens": result["input_tokens"],
                "output_tokens": result["output_tokens"],
                "total_tokens": result["total_tokens"],
                "cache_read_tokens": result["cache_read_tokens"],
                "cache_creation_tokens": result["cache_creation_tokens"],
            }

        else:  # manual
            start = time.time()
            input("\nPress Enter when stage is complete...")
            human_time = time.time() - start
            token_data = None

        exp.complete_stage(stage_id, human_time=human_time, token_data=token_data)

    exp.save_log()
    print("\nExperiment complete.")


if __name__ == "__main__":
    main()
