#!/usr/bin/env python3
"""CLI entry point for running benchmark experiments.

Supports:
  - Single-protocol runs (original mode)
  - Pipeline-driven execution with per-stage protocol slots
  - Git-based forking from existing experiment states
"""
import argparse
import sys
import time
import os

# Add parent to path so we can import harness as a package
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from harness.experiment import Experiment, setup_run_directory, load_task_config, resolve_pipeline
from harness.protocols import ALL_PROTOCOLS
from harness.claude_runner import run_headless, run_interactive


def list_protocols():
    """Print a table of all discovered protocols and exit."""
    if not ALL_PROTOCOLS:
        print("No protocols found.")
        return
    name_w = max(len(p.name) for p in ALL_PROTOCOLS.values())
    print(f"\n{'Protocol':<{name_w}}  Description")
    print(f"{'-'*name_w}  {'-'*50}")
    for proto in sorted(ALL_PROTOCOLS.values(), key=lambda p: p.name):
        custom = " [custom cmd]" if proto.custom_command else ""
        print(f"{proto.name:<{name_w}}  {proto.description}{custom}")
    print()


def list_pipelines(task_dir):
    """Print available pipelines for a task."""
    cfg = load_task_config(task_dir)
    pipelines = cfg.get("pipelines", {})
    if not pipelines:
        print(f"No pipelines defined in {task_dir}/task.yaml")
        return
    print(f"\nPipelines for {cfg.get('name', task_dir)}:")
    for name, pcfg in pipelines.items():
        stages = pcfg.get("stages", [])
        diff_type = pcfg.get("differential", "?")
        print(f"  {name:<30}  {diff_type:<12}  stages: {len(stages)}")
    print()


def parse_slots(slots_str):
    """Parse slot string like 'A=plan_and_implement,B=direct_tests_provided'."""
    if not slots_str:
        return {}
    slots = {}
    for pair in slots_str.split(","):
        pair = pair.strip()
        if "=" not in pair:
            raise ValueError(f"Invalid slot format: {pair} (expected SLOT=protocol)")
        key, val = pair.split("=", 1)
        slots[key.strip()] = val.strip()
    return slots


def run_stage(exp, stage_id, mode, protocol, timeout, special_stage=None, stage_index=None):
    """Run a single stage with the given mode and protocol. Returns metrics."""
    exp.prepare_stage(stage_id, special_stage=special_stage)
    prompt = exp.build_stage_prompt(stage_id, special_stage=special_stage)

    if mode == "headless":
        print(f"\nRunning headless Claude ({protocol.model}) for stage {stage_id}...")
        result = run_headless(exp.work_dir, prompt, protocol=protocol, timeout=timeout)
        human_time = result["wall_time_seconds"]
        wall_time = result["wall_time_seconds"]
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
        result = run_interactive(exp.work_dir, prompt, protocol=protocol)
        human_time = result["wall_time_seconds"]
        wall_time = result["wall_time_seconds"]
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
        wall_time = human_time
        token_data = None

    return exp.complete_stage(stage_id, human_time=human_time, wall_time=wall_time,
                              token_data=token_data, stage_index=stage_index)


def main():
    parser = argparse.ArgumentParser(description="Benchmark Harness")
    parser.add_argument("--list-protocols", action="store_true",
                        help="List all available protocols and exit")
    parser.add_argument("--list-pipelines", action="store_true",
                        help="List available pipelines for the task")
    parser.add_argument("--task-dir", help="Path to task directory")
    parser.add_argument("--protocol", choices=list(ALL_PROTOCOLS.keys()),
                        help="Protocol to use (required unless using --slots)")
    parser.add_argument("--pipeline", help="Pipeline to execute from task.yaml")
    parser.add_argument("--slots", help="Protocol slot assignments (e.g. A=proto1,B=proto2)")
    parser.add_argument("--fork-from", help="Fork from existing tree node ID (skip completed stages)")
    parser.add_argument("--work-dir", help="Working directory (default: auto-created under runs/)")
    parser.add_argument("--log-dir", help="Directory for log output (default: auto-created under runs/)")
    parser.add_argument("--engine-cmd", default="python3 minidb.py", help="Command to start the engine")
    parser.add_argument("--stages", nargs="*", help="Specific stages to run (default: all)")
    parser.add_argument("--mode", choices=["headless", "interactive", "manual"],
                        default=None, help="Run mode (default: interactive)")
    parser.add_argument("--timeout", type=int, default=None,
                        help="Timeout in seconds per stage for headless mode")
    parser.add_argument("--run-id", help="Custom run ID (default: auto-generated)")
    parser.add_argument("--model", help="Override model from protocol (e.g. claude-sonnet-4-6)")
    parser.add_argument("--ui", action="store_true",
                        help="Launch browser-based experiment UI instead of CLI")
    parser.add_argument("--port", type=int, default=8765,
                        help="Port for the web UI (default: 8765)")
    args = parser.parse_args()

    if args.list_protocols:
        list_protocols()
        return

    if args.list_pipelines:
        if not args.task_dir:
            parser.error("--task-dir is required with --list-pipelines")
        list_pipelines(args.task_dir)
        return

    # Web UI mode — protocol is optional (can be selected in browser)
    if args.ui:
        if not args.task_dir:
            parser.error("--task-dir is required (or use --list-protocols)")
        from harness.web_ui import launch_ui
        launch_ui(
            task_dir=args.task_dir,
            protocol_name=args.protocol,  # may be None
            work_dir=args.work_dir,
            log_dir=args.log_dir,
            engine_cmd=args.engine_cmd,
            model=args.model,
            run_id=args.run_id,
            port=args.port,
        )
        return

    # Parse slots
    slots = parse_slots(args.slots) if args.slots else {}

    # --protocol is required unless slots provide all protocols
    if not args.protocol and not slots:
        if not args.task_dir:
            parser.error("--task-dir and --protocol are required (or use --list-protocols)")
        parser.error("--protocol is required (or use --slots with --pipeline)")

    # If protocol not specified but slots are, use first slot's protocol as default
    protocol_name = args.protocol
    if not protocol_name and slots:
        protocol_name = list(slots.values())[0]

    protocol = ALL_PROTOCOLS[protocol_name]

    # Allow CLI model override
    if args.model:
        protocol.model = args.model

    # Determine run mode
    if args.mode:
        mode = args.mode
    elif protocol.human_supervised:
        mode = "interactive"
    else:
        mode = "interactive"

    # Set up run directory if work-dir/log-dir not explicitly provided
    if not args.work_dir or not args.log_dir:
        run_id = args.run_id or f"{protocol_name}_{int(time.time())}"
        dirs = setup_run_directory(run_id, args.task_dir, protocol)
        work_dir = args.work_dir or dirs["workspace"]
        log_dir = args.log_dir or dirs["results"]
    else:
        work_dir = args.work_dir
        log_dir = args.log_dir

    exp = Experiment(
        task_dir=args.task_dir,
        protocol_name=protocol_name,
        work_dir=work_dir,
        log_dir=log_dir,
        engine_cmd=args.engine_cmd,
        pipeline_name=args.pipeline,
        slots=slots,
    )
    exp.setup(fork_from_node=args.fork_from)

    # Pipeline-driven execution
    if args.pipeline and exp.pipeline_stages:
        print(f"\nExecuting pipeline: {args.pipeline}")
        for idx, ps in enumerate(exp.pipeline_stages):
            stage_id = ps["stage_id"]

            # Skip stages already completed via fork
            if stage_id in exp.completed_stages:
                print(f"\n  Skipping {stage_id} (completed via fork)")
                continue

            # Get per-stage protocol
            stage_protocol = exp.get_protocol_for_stage(stage_id)

            if ps["type"] == "parallel":
                # Run parallel stages
                exp.run_parallel_stages(
                    base_stage=exp.completed_stages[-1] if exp.completed_stages else None,
                    parallel_stages=ps["parallel"],
                )
            elif ps["type"] in ("translate", "refactor", "removal"):
                # Special stage
                special = {"type": ps["type"], "target": ps["target"], "id": ps["stage_id"]}
                run_stage(exp, stage_id, mode, stage_protocol, args.timeout,
                          special_stage=special, stage_index=idx)
            else:
                # Normal feature stage
                run_stage(exp, stage_id, mode, stage_protocol, args.timeout,
                          stage_index=idx)

    else:
        # Original execution mode: simple stage list
        stages = args.stages or exp.stages
        for idx, stage_id in enumerate(stages):
            run_stage(exp, stage_id, mode, protocol, args.timeout, stage_index=idx)

    exp.save_log()
    print("\nExperiment complete.")


if __name__ == "__main__":
    main()
