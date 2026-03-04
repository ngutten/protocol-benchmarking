"""Compute sequential, parallel, and round-trip differentials from experiment logs.

Notation follows the paper:
  M(Ta, Bb) = metrics after stage a with protocol T, then stage b with protocol B
  delta_seq = M(Ta, Bb) - M(Ba, Bb)
  delta_par = M(Ta, Bb||Bc) - M(Ba, Bb||Bc)
  delta_rt  = M(Ta, T^-1_a) - M(Ta)
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
        with open(f) as fh:
            logs.append(json.load(fh))
    return logs


def index_logs(logs):
    """Index logs by protocol -> {stage_id -> metrics_dict}."""
    index = {}
    for log in logs:
        protocol = log["protocol"]
        if protocol not in index:
            index[protocol] = {}
        for stage in log["stages"]:
            sid = stage["stage_id"]
            index[protocol][sid] = stage
    return index


COST_METRICS = ["human_time_seconds", "token_cost", "code_lines"]
QUALITY_METRICS = ["holdout_accuracy", "training_accuracy", "regression_rate"]
ALL_METRICS = COST_METRICS + QUALITY_METRICS


def sequential_differential(index, test_protocol, baseline_protocol, stage_a, stage_b):
    """Compute delta_seq for all metrics.
    
    Compares: running stage_a with test_protocol vs baseline_protocol,
    then measuring stage_b metrics.
    
    We need logs for:
      (test_protocol, stage_a) then (baseline_protocol, stage_b)
      (baseline_protocol, stage_a) then (baseline_protocol, stage_b)
    
    In practice, since stages are sequential within a single run, we compare
    the stage_b metrics from the test_protocol run vs the baseline_protocol run.
    The assumption is stage_b uses the same protocol in both cases (or we compare
    the full-protocol runs).
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


def compute_all_differentials(log_dir, baseline="direct_tests_provided"):
    """Compute all differentials from a directory of logs."""
    logs = load_logs(log_dir)
    if not logs:
        print("No logs found.")
        return []
    
    index = index_logs(logs)
    protocols = list(index.keys())
    all_results = []
    
    # Sequential differentials: compare each protocol against baseline
    stages = ["01_select_where", "02_order_limit", "03_aggregation",
              "04_join", "05_list_ops", "06_coercion"]
    
    for proto in protocols:
        if proto == baseline:
            continue
        for i in range(1, len(stages)):
            stage_a = stages[i - 1]
            stage_b = stages[i]
            diffs = sequential_differential(index, proto, baseline, stage_a, stage_b)
            all_results.extend(diffs)
    
    return all_results
