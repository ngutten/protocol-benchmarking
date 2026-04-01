#!/usr/bin/env python3
"""Generate all reference solutions for PDE solver tests.

Usage:
    python generate_all.py              # Run all stages
    python generate_all.py 1            # Run stage 1 only
    python generate_all.py 1 3          # Run stages 1 and 3
    python generate_all.py --list       # List all tests
"""

import sys
import os
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def main():
    from stage1_diffusion import run_all as run_stage1
    from stage2_multifield import run_all as run_stage2
    from stage3_general_pde import run_all as run_stage3
    stages = {
        1: ("Stage 1: Diffusion", run_stage1),
        2: ("Stage 2: Multiple Fields", run_stage2),
        3: ("Stage 3: General PDE", run_stage3),
    }

    if "--list" in sys.argv:
        print("Available stages:")
        for num, (name, _) in stages.items():
            print(f"  {num}: {name}")
        return

    # Parse which stages to run
    requested = []
    for arg in sys.argv[1:]:
        if arg.isdigit() and int(arg) in stages:
            requested.append(int(arg))
    if not requested:
        requested = [1, 2, 3]

    total_start = time.time()

    for stage_num in requested:
        name, runner = stages[stage_num]
        print(f"\n{'=' * 60}")
        print(f"  {name}")
        print(f"{'=' * 60}\n")
        start = time.time()
        runner()
        elapsed = time.time() - start
        print(f"\n  {name} completed in {elapsed:.1f}s")

    total = time.time() - total_start
    print(f"\n{'=' * 60}")
    print(f"  All requested stages completed in {total:.1f}s")
    print(f"  Output directory: {os.path.join(os.path.dirname(__file__), 'data')}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
