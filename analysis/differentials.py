"""Compute sequential, parallel, and round-trip differentials from experiment logs.

Notation follows the paper:
  M(Ta, Bb) = metrics after stage a with protocol T, then stage b with protocol B
  delta_seq = M(Ta, Bb) - M(Ba, Bb)
  delta_par = M(Ta, Bb||Bc) - M(Ba, Bb||Bc)
  delta_rt  = M(Ta, T^-1_a) - M(Ta)

Supports both flat logs (original single-protocol runs) and tree-based logs
(mixed-protocol pipeline runs with experiment_tree.json).
"""
import json
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from pathlib import Path


@dataclass
class DiffResult:
    """Result of a differential computation."""
    metric_name: str
    protocol_test: str
    protocol_baseline: str
    stage: str
    diff_type: str  # sequential, parallel, round_trip
    value_test: float
    value_baseline: float
    delta: float

    def __repr__(self):
        sign = "+" if self.delta > 0 else ""
        return f"{self.diff_type} {self.metric_name} @ {self.stage}: {sign}{self.delta:.4f} ({self.protocol_test} vs {self.protocol_baseline})"


def load_logs(log_dir):
    """Load all experiment logs from a directory."""
    logs = []
    log_dir = Path(log_dir)
    for f in sorted(log_dir.glob("*.json")):
        if f.name == "experiment_tree.json":
            continue  # skip the tree file
        with open(f) as fh:
            logs.append(json.load(fh))
    return logs


def load_tree(log_dir):
    """Load the experiment state tree if it exists."""
    tree_path = Path(log_dir) / "experiment_tree.json"
    if tree_path.exists():
        with open(tree_path) as f:
            return json.load(f)
    return None


def index_logs(logs):
    """Index logs by protocol -> {stage_id -> metrics_dict}.

    For mixed-protocol logs (pipeline runs with stage_protocols),
    indexes each stage under its actual protocol.
    """
    index = {}
    for log in logs:
        default_protocol = log["protocol"]
        stage_protocols = log.get("stage_protocols", {})

        for stage in log["stages"]:
            sid = stage["stage_id"]
            # Use per-stage protocol if available, else default
            protocol = stage_protocols.get(sid, stage.get("protocol", default_protocol))

            if protocol not in index:
                index[protocol] = {}
            index[protocol][sid] = stage
    return index


def index_logs_by_run(logs):
    """Index logs by run_id -> {stage_id -> metrics_dict}.

    Preserves the run context for tree-aware differentials.
    """
    index = {}
    for log in logs:
        run_id = log.get("run_id", "")
        if run_id not in index:
            index[run_id] = {
                "protocol": log["protocol"],
                "stage_protocols": log.get("stage_protocols", {}),
                "pipeline": log.get("pipeline"),
                "slots": log.get("slots", {}),
                "stages": {},
            }
        for stage in log["stages"]:
            index[run_id]["stages"][stage["stage_id"]] = stage
    return index


COST_METRICS = ["human_time_seconds", "wall_time_seconds", "token_cost",
                "effective_tokens", "code_lines"]
QUALITY_METRICS = ["holdout_accuracy", "training_accuracy", "regression_rate"]
ALL_METRICS = COST_METRICS + QUALITY_METRICS


def sequential_differential(index, test_protocol, baseline_protocol, stage_a, stage_b):
    """Compute delta_seq for all metrics.

    Compares: running stage_a with test_protocol vs baseline_protocol,
    then measuring stage_b metrics.

    For true sequential differentials with mixed protocols, we compare
    M(T_a, B_b) - M(B_a, B_b) by looking at the stage_b metrics from
    runs that differ only in which protocol was used for stage_a.
    """
    results = []

    test_stages = index.get(test_protocol, {})
    base_stages = index.get(baseline_protocol, {})

    if stage_b not in test_stages or stage_b not in base_stages:
        return results

    test_b = test_stages[stage_b]
    base_b = base_stages[stage_b]

    for metric in ALL_METRICS:
        tv = test_b.get(metric)
        bv = base_b.get(metric)
        if tv is not None and bv is not None:
            results.append(DiffResult(
                metric_name=metric,
                protocol_test=test_protocol,
                protocol_baseline=baseline_protocol,
                stage=stage_b,
                diff_type="sequential",
                value_test=tv,
                value_baseline=bv,
                delta=tv - bv,
            ))
    return results


def sequential_differential_mixed(run_index, test_run_id, baseline_run_id, stage_b):
    """Compute true sequential differential from mixed-protocol runs.

    Compares M(stage_b) between two runs that share the same pipeline
    but differ in protocol assignments for earlier stages.
    """
    results = []
    test_run = run_index.get(test_run_id)
    base_run = run_index.get(baseline_run_id)

    if not test_run or not base_run:
        return results

    test_stages = test_run["stages"]
    base_stages = base_run["stages"]

    if stage_b not in test_stages or stage_b not in base_stages:
        return results

    test_b = test_stages[stage_b]
    base_b = base_stages[stage_b]

    # Determine protocol labels for reporting
    test_proto = test_run.get("stage_protocols", {}).get(
        stage_b, test_run["protocol"])
    base_proto = base_run.get("stage_protocols", {}).get(
        stage_b, base_run["protocol"])

    for metric in ALL_METRICS:
        tv = test_b.get(metric)
        bv = base_b.get(metric)
        if tv is not None and bv is not None:
            results.append(DiffResult(
                metric_name=metric,
                protocol_test=f"{test_run_id}",
                protocol_baseline=f"{baseline_run_id}",
                stage=stage_b,
                diff_type="sequential",
                value_test=tv,
                value_baseline=bv,
                delta=tv - bv,
            ))
    return results


def parallel_differential(index, test_protocol, baseline_protocol, parallel_stages):
    """Compute delta_par for parallel stages.

    Compares merge metrics (conflicts, post-merge accuracy, regression)
    between test and baseline protocol runs.
    """
    results = []

    test_stages = index.get(test_protocol, {})
    base_stages = index.get(baseline_protocol, {})

    # Look for merge-related metrics in the parallel stages
    merge_metrics = ["merge_conflicts", "regression_rate"]

    for stage_id in parallel_stages:
        if stage_id not in test_stages or stage_id not in base_stages:
            continue
        test_s = test_stages[stage_id]
        base_s = base_stages[stage_id]

        for metric in merge_metrics + QUALITY_METRICS:
            tv = test_s.get(metric)
            bv = base_s.get(metric)
            if tv is not None and bv is not None:
                results.append(DiffResult(
                    metric_name=metric,
                    protocol_test=test_protocol,
                    protocol_baseline=baseline_protocol,
                    stage=stage_id,
                    diff_type="parallel",
                    value_test=tv,
                    value_baseline=bv,
                    delta=tv - bv,
                ))
    return results


def round_trip_differential(index, protocol, stage_before, stage_after_roundtrip):
    """Compute delta_rt = M(Ta, T^-1_a) - M(Ta).

    Compares metrics before and after a round-trip transformation.
    """
    results = []
    stages = index.get(protocol, {})

    if stage_before not in stages or stage_after_roundtrip not in stages:
        return results

    before = stages[stage_before]
    after = stages[stage_after_roundtrip]

    for metric in ALL_METRICS:
        bv = before.get(metric)
        av = after.get(metric)
        if bv is not None and av is not None:
            results.append(DiffResult(
                metric_name=metric,
                protocol_test=protocol,
                protocol_baseline=protocol,
                stage=f"{stage_before}->{stage_after_roundtrip}",
                diff_type="round_trip",
                value_test=av,
                value_baseline=bv,
                delta=av - bv,
            ))
    return results


def round_trip_from_compare(run_index, run_id, compare_spec):
    """Compute round-trip differential using a pipeline compare: block.

    Args:
        run_index: Index from index_logs_by_run().
        run_id: The run to analyze.
        compare_spec: Dict with 'before' and 'after' stage IDs,
                      optionally 'baseline' and 'metrics'.
    """
    results = []
    run = run_index.get(run_id)
    if not run:
        return results

    stages = run["stages"]
    before_id = compare_spec.get("before")
    after_id = compare_spec.get("after")
    baseline_id = compare_spec.get("baseline")
    metric_filter = compare_spec.get("metrics")

    if not before_id or not after_id:
        return results

    # Find the stages (may need to match numbered prefixes)
    before = _find_stage(stages, before_id)
    after = _find_stage(stages, after_id)
    baseline = _find_stage(stages, baseline_id) if baseline_id else None

    if not before or not after:
        return results

    ref = baseline if baseline else before
    metrics_to_check = metric_filter if metric_filter else ALL_METRICS

    for metric in metrics_to_check:
        rv = ref.get(metric)
        av = after.get(metric)
        if rv is not None and av is not None:
            results.append(DiffResult(
                metric_name=metric,
                protocol_test=run["protocol"],
                protocol_baseline=run["protocol"],
                stage=f"{before_id}->{after_id}",
                diff_type="round_trip",
                value_test=av,
                value_baseline=rv,
                delta=av - rv,
            ))
    return results


def _find_stage(stages_dict, stage_id):
    """Find a stage in a dict, matching either exact ID or suffix."""
    if stage_id in stages_dict:
        return stages_dict[stage_id]
    # Try matching by suffix (e.g. "aggregation" matches "03_aggregation")
    for sid, data in stages_dict.items():
        if sid.endswith(f"_{stage_id}") or sid == stage_id:
            return data
    return None


def compute_all_differentials(log_dir, baseline="direct_tests_provided"):
    """Compute all differentials from a directory of logs.

    Handles both flat single-protocol logs and mixed-protocol pipeline logs.
    Also reads pipeline configs from logs to compute round-trip differentials
    using compare: blocks.
    """
    logs = load_logs(log_dir)
    if not logs:
        print("No logs found.")
        return []

    index = index_logs(logs)
    run_index = index_logs_by_run(logs)
    tree = load_tree(log_dir)
    protocols = list(index.keys())
    all_results = []

    # Discover stages from baseline (or first available protocol)
    base_stages = index.get(baseline, {})
    if not base_stages:
        # Fall back to first protocol that has stages
        for p in protocols:
            if index[p]:
                base_stages = index[p]
                break
    stages = sorted(base_stages.keys())

    # Sequential differentials: compare each protocol against baseline
    for proto in protocols:
        if proto == baseline:
            continue
        # Direct per-stage comparison (same stage across protocols)
        for stage in stages:
            diffs = sequential_differential(index, proto, baseline, stage, stage)
            all_results.extend(diffs)

    # Mixed-protocol sequential differentials from pipeline runs
    pipeline_runs = [
        (rid, rdata) for rid, rdata in run_index.items()
        if rdata.get("stage_protocols")
    ]
    # Compare pipeline runs that share the same pipeline but differ in slots
    pipeline_groups = {}
    for rid, rdata in pipeline_runs:
        pipeline_name = rdata.get("pipeline", "")
        if pipeline_name:
            pipeline_groups.setdefault(pipeline_name, []).append((rid, rdata))

    for pipeline_name, runs in pipeline_groups.items():
        if len(runs) < 2:
            continue
        # Compare all pairs
        for i, (rid_a, rdata_a) in enumerate(runs):
            for rid_b, rdata_b in runs[i+1:]:
                # Find stages that exist in both runs
                common_stages = set(rdata_a["stages"].keys()) & set(rdata_b["stages"].keys())
                for stage in common_stages:
                    diffs = sequential_differential_mixed(run_index, rid_a, rid_b, stage)
                    all_results.extend(diffs)

    # Round-trip differentials from pipeline compare: blocks
    for rid, rdata in run_index.items():
        for log in logs:
            if log.get("run_id") == rid:
                pipeline_cfg = log.get("pipeline_config", {})
                compare_spec = pipeline_cfg.get("compare") if pipeline_cfg else None
                if compare_spec:
                    diffs = round_trip_from_compare(run_index, rid, compare_spec)
                    all_results.extend(diffs)
                break

    return all_results
