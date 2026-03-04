#!/usr/bin/env python3
"""Main analysis script: load logs, compute differentials, output tables and plots."""
import argparse
import json
import sys
import os
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from analysis.differentials import load_logs, index_logs, compute_all_differentials, ALL_METRICS


def print_summary_table(logs):
    """Print a summary table of all runs."""
    print("\n" + "=" * 80)
    print("EXPERIMENT SUMMARY")
    print("=" * 80)
    
    header = f"{'Protocol':<25} {'Stage':<20} {'Train':>7} {'Holdout':>7} {'Regress':>7} {'Lines':>6} {'Tokens':>8} {'Human(s)':>8}"
    print(header)
    print("-" * len(header))
    
    for log in logs:
        for stage in log["stages"]:
            ta = stage.get("training_accuracy")
            ha = stage.get("holdout_accuracy")
            rr = stage.get("regression_rate")
            ta_str = f"{ta:.0%}" if ta is not None else "N/A"
            ha_str = f"{ha:.0%}" if ha is not None else "N/A"
            rr_str = f"{rr:.0%}" if rr is not None else "N/A"
            print(f"{log['protocol']:<25} {stage['stage_id']:<20} {ta_str:>7} {ha_str:>7} {rr_str:>7} {stage.get('code_lines', 0):>6} {stage.get('token_cost', 0):>8} {stage.get('human_time_seconds', 0):>8.0f}")


def print_differentials(results):
    """Print differential results as a table."""
    if not results:
        print("\nNo differential results to display.")
        return
    
    print("\n" + "=" * 80)
    print("DIFFERENTIAL ANALYSIS")
    print("=" * 80)
    
    # Group by diff_type
    by_type = {}
    for r in results:
        by_type.setdefault(r.diff_type, []).append(r)
    
    for diff_type, diffs in by_type.items():
        print(f"\n--- {diff_type.upper()} DIFFERENTIALS ---")
        header = f"{'Metric':<25} {'Stage':<20} {'Test Proto':<20} {'Test':>8} {'Base':>8} {'Delta':>8}"
        print(header)
        print("-" * len(header))
        for d in diffs:
            sign = "+" if d.delta > 0 else ""
            print(f"{d.metric_name:<25} {d.stage:<20} {d.protocol_test:<20} {d.value_test:>8.3f} {d.value_baseline:>8.3f} {sign}{d.delta:>7.3f}")


def generate_plots(logs, output_dir):
    """Generate matplotlib plots if available."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("matplotlib not available, skipping plots.")
        return
    
    os.makedirs(output_dir, exist_ok=True)
    
    # Plot: accuracy by stage for each protocol
    fig, axes = plt.subplots(1, 2, figsize=(14, 6))
    
    for log in logs:
        proto = log["protocol"]
        stages = [s["stage_id"] for s in log["stages"]]
        train_acc = [s.get("training_accuracy", 0) or 0 for s in log["stages"]]
        holdout_acc = [s.get("holdout_accuracy", 0) or 0 for s in log["stages"]]
        
        axes[0].plot(range(len(stages)), train_acc, marker="o", label=proto)
        axes[1].plot(range(len(stages)), holdout_acc, marker="s", label=proto)
    
    for ax, title in zip(axes, ["Training Accuracy", "Holdout Accuracy"]):
        ax.set_title(title)
        ax.set_xlabel("Stage")
        ax.set_ylabel("Accuracy")
        ax.set_ylim(-0.05, 1.05)
        ax.legend(fontsize=8)
        if logs:
            stage_labels = [s["stage_id"][:10] for s in logs[0]["stages"]]
            ax.set_xticks(range(len(stage_labels)))
            ax.set_xticklabels(stage_labels, rotation=45, ha="right")
    
    plt.tight_layout()
    path = os.path.join(output_dir, "accuracy_by_stage.png")
    plt.savefig(path, dpi=150)
    print(f"Plot saved: {path}")
    plt.close()
    
    # Plot: regression rate
    fig, ax = plt.subplots(figsize=(10, 5))
    for log in logs:
        proto = log["protocol"]
        stages = [s["stage_id"] for s in log["stages"]]
        rr = [s.get("regression_rate", 0) or 0 for s in log["stages"]]
        ax.plot(range(len(stages)), rr, marker="^", label=proto)
    
    ax.set_title("Regression Rate by Stage")
    ax.set_xlabel("Stage")
    ax.set_ylabel("Regression Rate")
    ax.legend(fontsize=8)
    if logs:
        stage_labels = [s["stage_id"][:10] for s in logs[0]["stages"]]
        ax.set_xticks(range(len(stage_labels)))
        ax.set_xticklabels(stage_labels, rotation=45, ha="right")
    plt.tight_layout()
    path = os.path.join(output_dir, "regression_rate.png")
    plt.savefig(path, dpi=150)
    print(f"Plot saved: {path}")
    plt.close()

    # Plot: token cost
    fig, ax = plt.subplots(figsize=(10, 5))
    for log in logs:
        proto = log["protocol"]
        stages = [s["stage_id"] for s in log["stages"]]
        tokens = [s.get("token_cost", 0) for s in log["stages"]]
        ax.bar([f"{s[:8]}\n{proto[:8]}" for s in stages], tokens, label=proto, alpha=0.7)
    ax.set_title("Token Cost by Stage")
    ax.set_ylabel("Tokens")
    plt.xticks(rotation=45, ha="right")
    plt.tight_layout()
    path = os.path.join(output_dir, "token_cost.png")
    plt.savefig(path, dpi=150)
    print(f"Plot saved: {path}")
    plt.close()


def main():
    parser = argparse.ArgumentParser(description="Analyze MiniDB benchmark results")
    parser.add_argument("--log-dir", required=True, help="Directory containing experiment logs")
    parser.add_argument("--baseline", default="direct_tests_provided", help="Baseline protocol for differentials")
    parser.add_argument("--plots", default=None, help="Directory for plot output")
    parser.add_argument("--output-json", default=None, help="Write analysis results to JSON")
    args = parser.parse_args()
    
    logs = load_logs(args.log_dir)
    if not logs:
        print("No logs found in", args.log_dir)
        return
    
    print(f"Loaded {len(logs)} experiment logs.")
    print_summary_table(logs)
    
    diffs = compute_all_differentials(args.log_dir, baseline=args.baseline)
    print_differentials(diffs)
    
    if args.plots:
        generate_plots(logs, args.plots)
    
    if args.output_json:
        output = {
            "summary": [{
                "protocol": log["protocol"],
                "stages": log["stages"],
            } for log in logs],
            "differentials": [{
                "metric": d.metric_name,
                "stage": d.stage,
                "diff_type": d.diff_type,
                "test_protocol": d.protocol_test,
                "baseline_protocol": d.protocol_baseline,
                "delta": d.delta,
            } for d in diffs],
        }
        with open(args.output_json, "w") as f:
            json.dump(output, f, indent=2)
        print(f"\nResults written to {args.output_json}")


if __name__ == "__main__":
    main()
