"""Metric collection for benchmark harness.

Collects training, holdout, regression, and performance metrics for each stage.
Performance tests live in tests/perf/ and are auto-discovered by stage ID prefix.
"""
import subprocess
import json
import os
import re
import time as _time
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
class PerfResult:
    """Result from a single performance benchmark function."""
    name: str
    duration_seconds: float
    iterations: int = 1
    ops_per_second: float = 0.0
    stage: str = ""
    passed: bool = True
    error: str = ""


@dataclass
class StageMetrics:
    stage_id: str
    protocol: str
    human_time_seconds: float = 0.0
    wall_time_seconds: float = 0.0
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
    perf_tests_total: int = 0
    perf_tests_passed: int = 0
    perf_results: list = field(default_factory=list)
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

    def effective_tokens(self):
        """Cost-weighted token count: cache reads at 0.1x, everything else at 1x."""
        return (self.input_tokens + self.output_tokens
                + self.cache_creation_tokens
                + int(self.cache_read_tokens * 0.1))

    def perf_mean_duration(self):
        """Mean duration across all perf benchmarks (seconds)."""
        passed = [p for p in self.perf_results if isinstance(p, dict) and p.get("passed", True)]
        if not passed:
            passed = [p for p in self.perf_results if isinstance(p, PerfResult) and p.passed]
        if not passed:
            return None
        durations = []
        for p in passed:
            d = p["duration_seconds"] if isinstance(p, dict) else p.duration_seconds
            durations.append(d)
        return sum(durations) / len(durations) if durations else None

    def to_dict(self):
        d = asdict(self)
        d["training_accuracy"] = self.training_accuracy()
        d["holdout_accuracy"] = self.holdout_accuracy()
        d["regression_rate"] = self.regression_rate()
        d["token_cost"] = self.total_tokens  # backward compat key
        d["effective_tokens"] = self.effective_tokens()
        d["perf_mean_duration"] = self.perf_mean_duration()
        return d


def run_pytest(test_path, engine_cmd, conftest_dir=None, timeout=120):
    """Run pytest on a test file/dir and return structured results."""
    env = os.environ.copy()
    env["MINIDB_ENGINE_CMD"] = engine_cmd
    cmd = ["python3", "-m", "pytest", test_path, "-v", "--tb=short"]
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


def run_perf_tests(test_path, engine_cmd, conftest_dir=None, timeout=300):
    """Run performance benchmark tests and return timing results.

    Perf tests are standard pytest files in tests/perf/. Each test function
    exercises a workload and reports metrics by printing a JSON line to stdout:

        {
          "bench_metric": "ops_per_second",
          "test": "test_function_name",
          "value": 1234.5,
          "iterations": 1000,
          "duration_seconds": 0.812345
        }

    Fields:
        bench_metric: Always "ops_per_second" (the metric type).
        test: Name of the test function (matched against pytest's test ID).
        value: Operations per second (iterations / duration).
        iterations: Number of loop iterations in the benchmark.
        duration_seconds: Wall-clock time for the benchmark loop (preferred
            over pytest's --durations output for accuracy).

    Duration is also captured from pytest's --durations output as a fallback,
    but test-reported duration_seconds takes precedence.

    Returns:
        list[PerfResult]: One entry per test, with captured duration.
    """
    env = os.environ.copy()
    env["MINIDB_ENGINE_CMD"] = engine_cmd
    cmd = [
        "python3", "-m", "pytest", test_path,
        "-v", "-s", "--tb=short", "--durations=0",
    ]
    if conftest_dir:
        cmd.extend(["--rootdir", conftest_dir, "-c", "/dev/null"])
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, env=env,
                                timeout=timeout + 30)
    except subprocess.TimeoutExpired:
        return [PerfResult(name=test_path, duration_seconds=timeout,
                           passed=False, error="timeout")]

    results = []

    # Parse test pass/fail from verbose output.
    # With -s (no capture), pytest may split test name and status across lines:
    #   test_file.py::TestClass::test_name {stdout}
    #   PASSED
    test_status = {}
    current_test = None
    for line in result.stdout.splitlines():
        # Same-line match (no -s, or no stdout from test)
        m = re.match(r"(.+::\S+)\s+(PASSED|FAILED|ERROR|SKIPPED)", line)
        if m:
            test_status[m.group(1)] = m.group(2)
            current_test = None
            continue
        # Test name at start of line (with -s, stdout follows on same/next lines)
        m = re.match(r"(.+::\S+)\s", line)
        if m and "::" in m.group(1) and "/" in m.group(1):
            current_test = m.group(1)
            continue
        # Standalone status line (with -s)
        stripped = line.strip()
        if current_test and stripped in ("PASSED", "FAILED", "ERROR", "SKIPPED"):
            test_status[current_test] = stripped
            current_test = None

    # Parse durations from pytest's --durations output
    # Format: "N.NNs call     test_file.py::TestClass::test_name"
    duration_map = {}
    in_durations = False
    for line in result.stdout.splitlines():
        if "slowest durations" in line or "= slowest" in line:
            in_durations = True
            continue
        if in_durations:
            m = re.match(r"\s*([\d.]+)s\s+\w+\s+(.+::\S+)", line)
            if m:
                duration_map[m.group(2)] = float(m.group(1))
            elif line.strip().startswith("="):
                in_durations = False

    # Build PerfResult for each test
    for test_name, status in test_status.items():
        duration = duration_map.get(test_name, 0.0)
        results.append(PerfResult(
            name=test_name,
            duration_seconds=duration,
            passed=(status == "PASSED"),
            error="" if status == "PASSED" else status,
        ))

    # Check for custom bench_metric JSON in stdout.
    # With -s, the JSON may appear mid-line after the test name, so we
    # extract the first { ... } substring containing "bench_metric".
    for line in result.stdout.splitlines():
        if "bench_metric" not in line:
            continue
        # Find the JSON object in the line
        brace_start = line.find("{")
        if brace_start == -1:
            continue
        json_str = line[brace_start:]
        try:
            data = json.loads(json_str)
            # Find matching result and enrich it
            for r in results:
                if data.get("test") and data["test"] in r.name:
                    r.iterations = data.get("iterations", 1)
                    r.ops_per_second = data.get("value", 0.0)
                    # Prefer test-reported duration over pytest --durations
                    if data.get("duration_seconds"):
                        r.duration_seconds = data["duration_seconds"]
        except json.JSONDecodeError:
            pass

    return results


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
    # Match by stage_id or its numeric prefix (e.g. "06_coercion_rules" matches "test_06_coercion.py")
    stage_prefix = stage_id.split("_")[0] if "_" in stage_id else ""
    tp = os.path.join(test_dir, "training")
    for f in os.listdir(tp) if os.path.isdir(tp) else []:
        if (stage_id in f or (stage_prefix and re.match(rf"test_{stage_prefix}_", f))) and f.endswith(".py"):
            results, _ = run_pytest(os.path.join(tp, f), engine_cmd, conftest_dir)
            metrics.training_tests_total += len(results)
            metrics.training_tests_passed += sum(1 for r in results if r.passed)
            for r in results:
                r.stage, r.pool = stage_id, "training"
            metrics.test_results.extend(results)

    # Holdout tests for this stage
    hp = os.path.join(test_dir, "holdout")
    for f in os.listdir(hp) if os.path.isdir(hp) else []:
        if (stage_id in f or (stage_prefix and re.match(rf"test_{stage_prefix}_", f))) and f.endswith(".py"):
            results, _ = run_pytest(os.path.join(hp, f), engine_cmd, conftest_dir)
            metrics.holdout_tests_total += len(results)
            metrics.holdout_tests_passed += sum(1 for r in results if r.passed)
            for r in results:
                r.stage, r.pool = stage_id, "holdout"
            metrics.test_results.extend(results)

    # Regression: holdout tests from previous stages
    reg_total = reg_failed = 0
    for prev in previous_stages:
        prev_prefix = prev.split("_")[0] if "_" in prev else ""
        for f in os.listdir(hp) if os.path.isdir(hp) else []:
            if (prev in f or (prev_prefix and re.match(rf"test_{prev_prefix}_", f))) and f.endswith(".py"):
                results, _ = run_pytest(os.path.join(hp, f), engine_cmd, conftest_dir)
                reg_total += len(results)
                reg_failed += sum(1 for r in results if not r.passed)
                for r in results:
                    r.stage, r.pool = prev, "regression"
                metrics.test_results.extend(results)
    metrics.regression_tests_total = reg_total
    metrics.regression_tests_failed = reg_failed

    # Performance tests (holdout — never shown to LLM)
    pp = os.path.join(test_dir, "perf")
    if os.path.isdir(pp):
        for f in sorted(os.listdir(pp)):
            if not f.endswith(".py") or f.startswith("__"):
                continue
            # Match by stage_id or numeric prefix, same as holdout
            if stage_id in f or (stage_prefix and re.match(rf"test_{stage_prefix}_", f)):
                perf_results = run_perf_tests(os.path.join(pp, f), engine_cmd, conftest_dir)
                metrics.perf_tests_total += len(perf_results)
                metrics.perf_tests_passed += sum(1 for r in perf_results if r.passed)
                for r in perf_results:
                    r.stage = stage_id
                metrics.perf_results.extend(perf_results)

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
