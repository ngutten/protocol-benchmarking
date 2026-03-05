#!/usr/bin/env python3
"""Main analysis script: load logs, compute differentials, output tables and plots."""
import argparse
import json
import subprocess
import sys
import os
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from analysis.differentials import load_logs, index_logs, compute_all_differentials, ALL_METRICS


def _fmt_tokens(n):
    """Format token count with K/M suffix."""
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}K"
    return str(n)


def _fmt_time(s):
    """Format seconds as Xm Ys."""
    m, sec = divmod(int(s), 60)
    return f"{m}m {sec}s" if m else f"{sec}s"


def _effective_tokens(stage):
    """Cost-weighted tokens: cache reads at 0.1x, everything else at 1x."""
    return (stage.get("input_tokens", 0)
            + stage.get("output_tokens", 0)
            + stage.get("cache_creation_tokens", 0)
            + int(stage.get("cache_read_tokens", 0) * 0.1))


def print_summary_table(logs):
    """Print a summary table of all runs with full token breakdown."""
    print("\n" + "=" * 130)
    print("EXPERIMENT SUMMARY")
    print("=" * 130)

    header = (f"{'Protocol':<22} {'Stage':<18} {'Train':>6} {'Holdout':>7} {'Regr':>5}"
              f" {'Lines':>5} {'Wall':>7} {'Human':>7}"
              f" {'In':>7} {'Out':>7} {'C.Write':>8} {'C.Read':>8} {'Eff.Tok':>8}")
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
            wt = stage.get("wall_time_seconds", stage.get("human_time_seconds", 0))
            ht = stage.get("human_time_seconds", 0)
            eff = _effective_tokens(stage)
            print(f"{log['protocol']:<22} {stage['stage_id']:<18} {ta_str:>6} {ha_str:>7} {rr_str:>5}"
                  f" {stage.get('code_lines', 0):>5} {_fmt_time(wt):>7} {_fmt_time(ht):>7}"
                  f" {_fmt_tokens(stage.get('input_tokens', 0)):>7}"
                  f" {_fmt_tokens(stage.get('output_tokens', 0)):>7}"
                  f" {_fmt_tokens(stage.get('cache_creation_tokens', 0)):>8}"
                  f" {_fmt_tokens(stage.get('cache_read_tokens', 0)):>8}"
                  f" {_fmt_tokens(eff):>8}")

    # Per-protocol totals
    print()
    print("--- Totals per protocol ---")
    header2 = f"{'Protocol':<22} {'Stages':>6} {'Wall':>7} {'Human':>7} {'In':>7} {'Out':>7} {'C.Write':>8} {'C.Read':>8} {'Eff.Tok':>8}"
    print(header2)
    print("-" * len(header2))
    for log in logs:
        stages = [s for s in log["stages"] if not s.get("skipped")]
        n = len(stages)
        wt = sum(s.get("wall_time_seconds", s.get("human_time_seconds", 0)) for s in stages)
        ht = sum(s.get("human_time_seconds", 0) for s in stages)
        inp = sum(s.get("input_tokens", 0) for s in stages)
        out = sum(s.get("output_tokens", 0) for s in stages)
        cw = sum(s.get("cache_creation_tokens", 0) for s in stages)
        cr = sum(s.get("cache_read_tokens", 0) for s in stages)
        eff = sum(_effective_tokens(s) for s in stages)
        print(f"{log['protocol']:<22} {n:>6} {_fmt_time(wt):>7} {_fmt_time(ht):>7}"
              f" {_fmt_tokens(inp):>7} {_fmt_tokens(out):>7}"
              f" {_fmt_tokens(cw):>8} {_fmt_tokens(cr):>8} {_fmt_tokens(eff):>8}")


def print_differentials(results):
    """Print differential results as a table."""
    if not results:
        print("\nNo differential results to display.")
        return

    print("\n" + "=" * 100)
    print("DIFFERENTIAL ANALYSIS")
    print("=" * 100)

    # Group by diff_type
    by_type = {}
    for r in results:
        by_type.setdefault(r.diff_type, []).append(r)

    for diff_type, diffs in by_type.items():
        print(f"\n--- {diff_type.upper()} DIFFERENTIALS ---")
        header = f"{'Metric':<25} {'Stage':<20} {'Test Proto':<20} {'Test':>10} {'Base':>10} {'Delta':>10}"
        print(header)
        print("-" * len(header))
        for d in diffs:
            sign = "+" if d.delta > 0 else ""
            print(f"{d.metric_name:<25} {d.stage:<20} {d.protocol_test:<20} {d.value_test:>10.3f} {d.value_baseline:>10.3f} {sign}{d.delta:>9.3f}")


def generate_plots(logs, output_dir):
    """Generate matplotlib plots."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import numpy as np
    except ImportError:
        print("matplotlib not available, skipping plots.")
        return

    os.makedirs(output_dir, exist_ok=True)

    # ---- Plot 1: Accuracy by stage ----
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

    # ---- Plot 2: Regression rate ----
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

    # ---- Plot 3: Token breakdown (stacked bar) ----
    fig, ax = plt.subplots(figsize=(12, 6))
    x_labels = []
    inp_vals, out_vals, cw_vals, cr_vals = [], [], [], []
    for log in logs:
        proto = log["protocol"]
        for s in log["stages"]:
            x_labels.append(f"{s['stage_id'][:8]}\n{proto[:12]}")
            inp_vals.append(s.get("input_tokens", 0))
            out_vals.append(s.get("output_tokens", 0))
            cw_vals.append(s.get("cache_creation_tokens", 0))
            cr_vals.append(s.get("cache_read_tokens", 0))

    x = np.arange(len(x_labels))
    width = 0.6
    inp_arr = np.array(inp_vals)
    out_arr = np.array(out_vals)
    cw_arr = np.array(cw_vals)
    cr_arr = np.array(cr_vals)

    ax.bar(x, inp_arr, width, label="Input", color="#3b82f6")
    ax.bar(x, out_arr, width, bottom=inp_arr, label="Output", color="#22c55e")
    ax.bar(x, cw_arr, width, bottom=inp_arr + out_arr, label="Cache Write", color="#f59e0b")
    ax.bar(x, cr_arr, width, bottom=inp_arr + out_arr + cw_arr, label="Cache Read", color="#a78bfa", alpha=0.7)

    ax.set_title("Token Breakdown by Stage")
    ax.set_ylabel("Tokens")
    ax.set_xticks(x)
    ax.set_xticklabels(x_labels, rotation=45, ha="right", fontsize=8)
    ax.legend()
    plt.tight_layout()
    path = os.path.join(output_dir, "token_breakdown.png")
    plt.savefig(path, dpi=150)
    print(f"Plot saved: {path}")
    plt.close()

    # ---- Plot 4: Effective token cost ----
    fig, ax = plt.subplots(figsize=(10, 5))
    for log in logs:
        proto = log["protocol"]
        stages = [s["stage_id"] for s in log["stages"]]
        eff = [_effective_tokens(s) for s in log["stages"]]
        ax.bar([f"{sid[:8]}\n{proto[:8]}" for sid in stages], eff, label=proto, alpha=0.7)
    ax.set_title("Effective Token Cost by Stage (cache reads at 0.1x)")
    ax.set_ylabel("Effective Tokens")
    plt.xticks(rotation=45, ha="right")
    plt.tight_layout()
    path = os.path.join(output_dir, "effective_tokens.png")
    plt.savefig(path, dpi=150)
    print(f"Plot saved: {path}")
    plt.close()

    # ---- Plot 5: Time by stage (wall clock + human time) ----
    fig, axes = plt.subplots(1, 2, figsize=(14, 6))
    for log in logs:
        proto = log["protocol"]
        stages = [s["stage_id"] for s in log["stages"]]
        wall = [s.get("wall_time_seconds", s.get("human_time_seconds", 0)) for s in log["stages"]]
        human = [s.get("human_time_seconds", 0) for s in log["stages"]]
        axes[0].plot(range(len(stages)), wall, marker="o", label=proto)
        axes[1].plot(range(len(stages)), human, marker="s", label=proto)
    for ax, title in zip(axes, ["Wall Clock Time", "Human Time"]):
        ax.set_title(title)
        ax.set_xlabel("Stage")
        ax.set_ylabel("Seconds")
        ax.legend(fontsize=8)
        if logs:
            stage_labels = [s["stage_id"][:10] for s in logs[0]["stages"]]
            ax.set_xticks(range(len(stage_labels)))
            ax.set_xticklabels(stage_labels, rotation=45, ha="right")
    plt.tight_layout()
    path = os.path.join(output_dir, "time_by_stage.png")
    plt.savefig(path, dpi=150)
    print(f"Plot saved: {path}")
    plt.close()

    # ---- Plot 6: Cumulative time ----
    fig, ax = plt.subplots(figsize=(10, 5))
    for log in logs:
        proto = log["protocol"]
        stages = [s["stage_id"] for s in log["stages"]]
        wall = [s.get("wall_time_seconds", s.get("human_time_seconds", 0)) for s in log["stages"]]
        cumulative = []
        total = 0
        for w in wall:
            total += w
            cumulative.append(total)
        ax.plot(range(len(stages)), cumulative, marker="D", label=proto)
    ax.set_title("Cumulative Wall Clock Time")
    ax.set_xlabel("Stage")
    ax.set_ylabel("Total Seconds")
    ax.legend(fontsize=8)
    if logs:
        stage_labels = [s["stage_id"][:10] for s in logs[0]["stages"]]
        ax.set_xticks(range(len(stage_labels)))
        ax.set_xticklabels(stage_labels, rotation=45, ha="right")
    plt.tight_layout()
    path = os.path.join(output_dir, "cumulative_time.png")
    plt.savefig(path, dpi=150)
    print(f"Plot saved: {path}")
    plt.close()


def generate_latex_table(logs, output_path, diffs=None):
    """Generate a LaTeX summary table and compile to PDF."""
    output_path = Path(output_path)
    tex_path = output_path.with_suffix(".tex")

    # Escape LaTeX special chars
    def esc(s):
        return s.replace("_", r"\_").replace("%", r"\%").replace("&", r"\&")

    lines = [
        r"\documentclass[11pt,landscape]{article}",
        r"\usepackage[margin=1.5cm]{geometry}",
        r"\usepackage{booktabs}",
        r"\usepackage{longtable}",
        r"\usepackage{tabularx}",
        r"\usepackage{xcolor}",
        r"\usepackage{colortbl}",
        r"\definecolor{pass}{HTML}{22c55e}",
        r"\definecolor{fail}{HTML}{ef4444}",
        r"\newcolumntype{R}{>{\raggedleft\arraybackslash}X}",
        r"\begin{document}",
        r"\pagestyle{empty}",
        r"",
        r"\section*{Experiment Results Summary}",
        r"",
        # Per-stage table — tabularx stretches to full page width
        r"\small",
        r"\begin{tabularx}{\textwidth}{@{}l l R R R R R R R R R R@{}}",
        r"\toprule",
        r"& & \multicolumn{3}{c}{\textbf{Accuracy}} & \multicolumn{2}{c}{\textbf{Time (s)}} & \multicolumn{4}{c}{\textbf{Token Breakdown}} & \textbf{Eff.} \\",
        r"\cmidrule(lr){3-5} \cmidrule(lr){6-7} \cmidrule(lr){8-11} \cmidrule(lr){12-12}",
        r"Protocol & Stage & Train & Hold. & Regr. & Wall & Human & In & Out & C.Write & C.Read & Tokens \\",
        r"\midrule",
    ]

    for log in logs:
        for i, stage in enumerate(log["stages"]):
            ta = stage.get("training_accuracy")
            ha = stage.get("holdout_accuracy")
            rr = stage.get("regression_rate")
            ta_str = f"{ta*100:.0f}\\%" if ta is not None else "--"
            ha_str = f"{ha*100:.0f}\\%" if ha is not None else "--"
            rr_str = f"{rr*100:.0f}\\%" if rr is not None else "--"
            wt = stage.get("wall_time_seconds", stage.get("human_time_seconds", 0))
            ht = stage.get("human_time_seconds", 0)
            eff = _effective_tokens(stage)

            proto_col = esc(log["protocol"]) if i == 0 else ""
            lines.append(
                f"{proto_col} & {esc(stage['stage_id'])} & "
                f"{ta_str} & {ha_str} & {rr_str} & "
                f"{wt:.0f} & {ht:.0f} & "
                f"{_fmt_tokens(stage.get('input_tokens', 0))} & "
                f"{_fmt_tokens(stage.get('output_tokens', 0))} & "
                f"{_fmt_tokens(stage.get('cache_creation_tokens', 0))} & "
                f"{_fmt_tokens(stage.get('cache_read_tokens', 0))} & "
                f"{_fmt_tokens(eff)} \\\\"
            )
        lines.append(r"\midrule")

    # Totals section
    lines.append(r"\multicolumn{12}{l}{\textbf{Protocol Totals}} \\")
    lines.append(r"\midrule")
    for log in logs:
        stages = [s for s in log["stages"] if not s.get("skipped")]
        wt = sum(s.get("wall_time_seconds", s.get("human_time_seconds", 0)) for s in stages)
        ht = sum(s.get("human_time_seconds", 0) for s in stages)
        inp = sum(s.get("input_tokens", 0) for s in stages)
        out = sum(s.get("output_tokens", 0) for s in stages)
        cw = sum(s.get("cache_creation_tokens", 0) for s in stages)
        cr = sum(s.get("cache_read_tokens", 0) for s in stages)
        eff = sum(_effective_tokens(s) for s in stages)
        ta_avg = [s.get("training_accuracy") for s in stages if s.get("training_accuracy") is not None]
        ha_avg = [s.get("holdout_accuracy") for s in stages if s.get("holdout_accuracy") is not None]
        ta_str = f"{sum(ta_avg)/len(ta_avg)*100:.0f}\\%" if ta_avg else "--"
        ha_str = f"{sum(ha_avg)/len(ha_avg)*100:.0f}\\%" if ha_avg else "--"
        lines.append(
            f"\\textbf{{{esc(log['protocol'])}}} & \\textit{{total}} & "
            f"{ta_str} & {ha_str} & -- & "
            f"{wt:.0f} & {ht:.0f} & "
            f"{_fmt_tokens(inp)} & {_fmt_tokens(out)} & "
            f"{_fmt_tokens(cw)} & {_fmt_tokens(cr)} & {_fmt_tokens(eff)} \\\\"
        )

    lines.extend([
        r"\bottomrule",
        r"\end{tabularx}",
    ])

    # Differentials table
    if diffs:
        lines.extend([
            r"",
            r"\section*{Differential Analysis (vs.\ baseline)}",
            r"\small",
            r"\begin{tabularx}{\textwidth}{@{}l l l l R R R@{}}",
            r"\toprule",
            r"Type & Metric & Stage & Test Protocol & Test & Base & $\Delta$ \\",
            r"\midrule",
        ])
        for d in diffs:
            sign = "+" if d.delta > 0 else ""
            lines.append(
                f"{d.diff_type} & {esc(d.metric_name)} & {esc(d.stage)} & "
                f"{esc(d.protocol_test)} & {d.value_test:.3f} & "
                f"{d.value_baseline:.3f} & {sign}{d.delta:.3f} \\\\"
            )
        lines.extend([
            r"\bottomrule",
            r"\end{tabularx}",
        ])

    lines.extend([
        r"",
        r"\end{document}",
    ])

    tex_content = "\n".join(lines)
    tex_path.write_text(tex_content)
    print(f"LaTeX source: {tex_path}")

    # Try to compile to PDF
    pdf_path = output_path.with_suffix(".pdf")
    try:
        result = subprocess.run(
            ["pdflatex", "-interaction=nonstopmode", "-output-directory",
             str(tex_path.parent), str(tex_path)],
            capture_output=True, text=True, timeout=30,
        )
        if pdf_path.exists():
            print(f"PDF report:   {pdf_path}")
            # Clean up aux files
            for ext in [".aux", ".log", ".out"]:
                aux = output_path.with_suffix(ext)
                if aux.exists():
                    aux.unlink()
        else:
            print(f"pdflatex failed (PDF not created). LaTeX source saved at {tex_path}")
            if result.stderr:
                print(f"  stderr: {result.stderr[:200]}")
    except FileNotFoundError:
        print("pdflatex not found. Install texlive to generate PDF. LaTeX source saved.")
    except subprocess.TimeoutExpired:
        print("pdflatex timed out. LaTeX source saved.")


def main():
    parser = argparse.ArgumentParser(description="Analyze MiniDB benchmark results")
    parser.add_argument("--log-dir", required=True, help="Directory containing experiment logs")
    parser.add_argument("--baseline", default="direct_tests_provided", help="Baseline protocol for differentials")
    parser.add_argument("--plots", default=None, help="Directory for plot output")
    parser.add_argument("--output-json", default=None, help="Write analysis results to JSON")
    parser.add_argument("--latex", default=None,
                        help="Output path for LaTeX/PDF summary (e.g. reports/summary)")
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

    if args.latex:
        generate_latex_table(logs, args.latex, diffs=diffs)

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
