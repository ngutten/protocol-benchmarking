# Supplementary Evaluations: Performance Benchmarks & Custom Metrics

This document describes how to build standardized supplementary evaluations
(performance benchmarks, speed tests, etc.) into benchmark tasks and wire
them up for automatic discovery and execution by the harness.

## Overview

Every task stage can have three test pools:

| Pool | Directory | Shown to LLM | Purpose |
|------|-----------|---------------|---------|
| **training** | `tests/training/` | Yes (if protocol allows) | Guide implementation |
| **holdout** | `tests/holdout/` | Never | Correctness evaluation |
| **perf** | `tests/perf/` | Never | Runtime speed measurement |

Performance tests are **holdout by design** — they are never copied to the
workspace or shown to the LLM. They measure the runtime characteristics of
the code the LLM produced, giving an objective speed metric per stage.

## Directory Layout

```
tasks/<task_name>/
├── task.yaml
├── tests/
│   ├── conftest.py          # Shared fixtures (engine harness, etc.)
│   ├── training/
│   │   └── test_01_stage_name.py
│   ├── holdout/
│   │   └── test_01_stage_name_holdout.py
│   └── perf/                        # <-- NEW
│       └── test_01_stage_name_perf.py
```

## Naming Convention

Perf test files follow the same naming pattern as training/holdout tests:

```
test_{NN}_{stage_id}_perf.py
```

The harness auto-discovers perf tests by matching the stage's numeric prefix
(e.g., `01`) or full stage ID (e.g., `select_where`) against filenames in
`tests/perf/`. No additional configuration is required beyond placing the
file in the right directory.

## Declaring in task.yaml (Optional)

While auto-discovery works without it, you can explicitly declare perf tests
in `task.yaml` for documentation and validation:

```yaml
stages:
  - id: select_where
    spec: stages/01_select_where.md
    type: feature_addition
    training_tests: tests/training/test_01_select_where.py
    holdout_tests: tests/holdout/test_01_select_where_holdout.py
    perf_tests: tests/perf/test_01_select_where_perf.py    # optional, for docs
```

## Writing Performance Tests

Perf tests are standard pytest files that use the same fixtures as
training/holdout tests. The key difference: they exercise **workloads**
designed to measure throughput and latency rather than correctness edges.

### Basic Structure

```python
"""Performance benchmarks for Stage 1: SELECT / WHERE."""
import time


class TestSelectThroughput:
    def _populate(self, engine, n=200):
        """Helper to insert test data."""
        engine.execute("CREATE TABLE perf (id, name, value)")
        for i in range(n):
            engine.execute(f"INSERT INTO perf VALUES ({i}, 'u_{i}', {i * 1.1})")

    def test_where_filter_200_rows(self, engine):
        """WHERE filter on 200 rows, repeated 10 times."""
        self._populate(engine, 200)
        start = time.perf_counter()
        for _ in range(10):
            engine.query_rows("SELECT id, name FROM perf WHERE value > 100")
        elapsed = time.perf_counter() - start
        # Optional: print machine-readable metric
        print(f'{{"bench_metric": "ops_per_second", '
              f'"test": "test_where_filter_200_rows", '
              f'"value": {10 / elapsed:.2f}, "iterations": 10}}')
```

### Guidelines

1. **Use `time.perf_counter()`** for timing, not `time.time()`.

2. **Repeat operations** in a loop (10-20 iterations) to reduce noise.
   A single operation may be dominated by subprocess I/O overhead.

3. **Include a correctness assertion** so the test fails if the feature
   is broken (e.g., `assert len(rows) == 50`). A perf test that passes
   on broken code is useless.

4. **Scale data realistically.** 100-500 rows is a good range — enough to
   measure algorithmic differences without making tests slow. Keep total
   perf suite runtime under 60 seconds per stage.

5. **One concern per test.** Measure INSERT throughput separately from
   SELECT throughput, JOINs separately from aggregations, etc.

### Custom Metrics (Optional)

Tests can emit structured JSON to stdout to report custom metrics:

```python
print('{"bench_metric": "ops_per_second", '
      '"test": "test_bulk_insert", '
      '"value": 1234.5, '
      '"iterations": 1000}')
```

Fields:
- `bench_metric`: Metric name (e.g., `"ops_per_second"`, `"latency_ms"`)
- `test`: Test function name (used to match back to the PerfResult)
- `value`: Numeric value
- `iterations`: Number of iterations the value represents

These are captured in the `PerfResult.ops_per_second` and
`PerfResult.iterations` fields in the metrics output.

## How the Harness Runs Perf Tests

After each stage completes, `collect_stage_metrics()` in `harness/metrics.py`:

1. Scans `tests/perf/` for files matching the current stage ID
2. Runs them with pytest (`-v --tb=short --durations=0`)
3. Parses pass/fail status and durations from pytest output
4. Parses any `bench_metric` JSON lines from stdout
5. Records results as `PerfResult` objects in `StageMetrics.perf_results`

The perf results appear in:
- **Console output** during the run (per-benchmark timing breakdown)
- **JSON log** (`StageMetrics.perf_results`, `perf_tests_total`, `perf_tests_passed`)
- **Computed metrics**: `perf_mean_duration` (average duration across passing benchmarks)

## Metrics Available in Logs

Each stage's JSON log entry includes:

```json
{
  "perf_tests_total": 5,
  "perf_tests_passed": 5,
  "perf_mean_duration": 0.342,
  "perf_results": [
    {
      "name": "test_01_select_where_perf.py::TestInsertThroughput::test_bulk_insert_100",
      "duration_seconds": 0.45,
      "iterations": 100,
      "ops_per_second": 222.5,
      "stage": "01_select_where",
      "passed": true,
      "error": ""
    }
  ]
}
```

## Adding Perf Tests to a New Task

1. Create `tests/perf/` in your task's test directory
2. Add `conftest.py` (or symlink the existing one) if your perf tests use
   the same fixtures
3. Write perf test files following the naming convention
4. Optionally declare `perf_tests:` in `task.yaml` stages
5. Run the harness — perf tests are discovered and executed automatically

No changes to the harness code are needed.

## Adding a New Supplementary Evaluation Type

The perf system is a concrete instance of the general pattern for
supplementary holdout evaluations. To add a new type:

1. **Create a directory** under `tests/` (e.g., `tests/memory/`,
   `tests/security/`)
2. **Add a runner function** in `harness/metrics.py` (follow `run_perf_tests`
   as a template)
3. **Add fields** to `StageMetrics` for the new metric type
4. **Wire discovery** into `collect_stage_metrics()` — scan the directory,
   match by stage ID prefix
5. **Update `to_dict()`** to include any computed summary metrics
6. **Document** the convention in this file

The key principle: supplementary evaluations are always holdout (never shown
to the LLM) and are automatically discovered by filename convention.
