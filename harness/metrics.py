"""Metric collection for MiniDB benchmark harness."""
import subprocess
import json
import os
import re
from dataclasses import dataclass, field, asdict
from typing import Optional


@dataclass
class TestResult:
    name: str
    passed: bool
    duration: float = 0.0
    stage: str = ""
    pool: str = ""  # training, holdout, regression


@dataclass
class StageMetrics:
    stage_id: str
    protocol: str
    human_time_seconds: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_creation_tokens: int = 0
    total_tokens: int = 0
    training_tests_total: int = 0
    training_tests_passed: int = 0
    holdout_tests_total: int = 0
    holdout_tests_passed: int = 0
    regression_tests_total: int = 0
    regression_tests_failed: int = 0
    code_lines: int = 0
    code_bytes: int = 0
    git_commit: str = ""
    git_tag: str = ""
    merge_conflicts: int = 0
    merge_conflict_files: list = field(default_factory=list)
    test_results: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    start_time: str = ""
    end_time: str = ""

    def training_accuracy(self):
        return self.training_tests_passed / self.training_tests_total if self.training_tests_total else None

    def holdout_accuracy(self):
        return self.holdout_tests_passed / self.holdout_tests_total if self.holdout_tests_total else None

    def regression_rate(self):
        return self.regression_tests_failed / self.regression_tests_total if self.regression_tests_total else 0.0

    @property
    def token_cost(self):
        """Backward-compatible alias for total_tokens."""
        return self.total_tokens

    @token_cost.setter
    def token_cost(self, value):
        self.total_tokens = value

    def to_dict(self):
        d = asdict(self)
        d["training_accuracy"] = self.training_accuracy()
        d["holdout_accuracy"] = self.holdout_accuracy()
        d["regression_rate"] = self.regression_rate()
        d["token_cost"] = self.total_tokens  # backward compat key
        return d


def run_pytest(test_path, engine_cmd, conftest_dir=None, timeout=120):
    """Run pytest on a test file/dir and return structured results."""
    env = os.environ.copy()
    env["MINIDB_ENGINE_CMD"] = engine_cmd
    cmd = ["python3", "-m", "pytest", test_path, "-v", "--tb=short", "-q"]
    if conftest_dir:
        cmd.extend(["--rootdir", conftest_dir, "-c", "/dev/null"])
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=timeout + 30)
    except subprocess.TimeoutExpired:
        return [], 1
    tests = []
    for line in result.stdout.splitlines():
        m = re.match(r"(.+::\S+)\s+(PASSED|FAILED|ERROR|SKIPPED)", line)
        if m:
            tests.append(TestResult(
                name=m.group(1), passed=(m.group(2) == "PASSED"),
            ))
    return tests, result.returncode


def count_code(project_dir, extensions=(".py", ".cpp", ".cc", ".h", ".hpp", ".rs", ".ts", ".js")):
    """Count lines and bytes of source code."""
    total_lines = 0
    total_bytes = 0
    for root, dirs, fnames in os.walk(project_dir):
        dirs[:] = [d for d in dirs if not d.startswith(".") and d not in ("__pycache__", "tests", "test", ".git")]
        for fname in fnames:
            if any(fname.endswith(ext) for ext in extensions):
                path = os.path.join(root, fname)
                try:
                    content = open(path).read()
                    total_lines += len(content.splitlines())
                    total_bytes += len(content.encode("utf-8"))
                except Exception:
                    pass
    return total_lines, total_bytes


def collect_stage_metrics(stage_id, protocol, project_dir, test_dir, engine_cmd, previous_stages):
    """Collect all metrics after a completed stage."""
    metrics = StageMetrics(stage_id=stage_id, protocol=protocol)
    metrics.code_lines, metrics.code_bytes = count_code(project_dir)

    conftest_dir = test_dir

    # Training tests for this stage
    tp = os.path.join(test_dir, "training")
    for f in os.listdir(tp) if os.path.isdir(tp) else []:
        if stage_id in f and f.endswith(".py"):
            results, _ = run_pytest(os.path.join(tp, f), engine_cmd, conftest_dir)
            metrics.training_tests_total += len(results)
            metrics.training_tests_passed += sum(1 for r in results if r.passed)
            for r in results:
                r.stage, r.pool = stage_id, "training"
            metrics.test_results.extend(results)

    # Holdout tests for this stage
    hp = os.path.join(test_dir, "holdout")
    for f in os.listdir(hp) if os.path.isdir(hp) else []:
        if stage_id in f and f.endswith(".py"):
            results, _ = run_pytest(os.path.join(hp, f), engine_cmd, conftest_dir)
            metrics.holdout_tests_total += len(results)
            metrics.holdout_tests_passed += sum(1 for r in results if r.passed)
            for r in results:
                r.stage, r.pool = stage_id, "holdout"
            metrics.test_results.extend(results)

    # Regression: holdout tests from previous stages
    reg_total = reg_failed = 0
    for prev in previous_stages:
        for f in os.listdir(hp) if os.path.isdir(hp) else []:
            if prev in f and f.endswith(".py"):
                results, _ = run_pytest(os.path.join(hp, f), engine_cmd, conftest_dir)
                reg_total += len(results)
                reg_failed += sum(1 for r in results if not r.passed)
                for r in results:
                    r.stage, r.pool = prev, "regression"
                metrics.test_results.extend(results)
    metrics.regression_tests_total = reg_total
    metrics.regression_tests_failed = reg_failed

    # Git info
    try:
        metrics.git_commit = subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, cwd=project_dir
        ).stdout.strip()
    except Exception:
        pass

    return metrics


def detect_merge_conflicts(project_dir):
    """Count conflict markers in working tree after a merge."""
    conflicts = 0
    conflict_files = []
    for root, dirs, fnames in os.walk(project_dir):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for fname in fnames:
            path = os.path.join(root, fname)
            try:
                content = open(path).read()
                if "<<<<<<<" in content and ">>>>>>>" in content:
                    conflicts += content.count("<<<<<<<")
                    conflict_files.append(os.path.relpath(path, project_dir))
            except Exception:
                pass
    return conflicts, conflict_files
