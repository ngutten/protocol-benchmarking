# PDE Solver

A progressive benchmark for building a two-dimensional partial differential equation solver, implemented as a pure Python library (called by test code, not a standalone script).

## Overview

The solver operates on scalar and vector fields defined on two-dimensional grids. It must support a variety of boundary conditions, time-stepping schemes, and equation types ranging from simple heat diffusion to fully general nonlinear PDEs specified via callable expressions.

## Stage Progression

| Stage | Focus | Key Capability |
|-------|-------|----------------|
| 1 | Diffusion on a square grid | Time-dependent heat equation with four BC types |
| 2 | Multiple fields and equation types | Poisson, vector fields, static fields, adaptive timestepping |
| 3 | General PDEs | Arbitrary nonlinearities, differential operators, user-defined parameters |

## Entry Point

The solver is a Python library. Test code imports it directly:

```python
import pdesolver
```

## Validation Approach

Tests compare solver output against precomputed reference solutions. The reference code lives alongside the tests and produces ground-truth data for each scenario. Numerical results are expected to agree within **10% relative tolerance** of the reference (or 10% absolute tolerance when values are near zero). This ensures the solver uses correct numerical methods without requiring exact algorithmic matching.

Tests prioritize:
- **Correctness**: solutions match reference data
- **Stability**: solvers do not diverge for well-posed problems
- **Convergence**: refining grids or timesteps improves accuracy at expected rates
- **Robustness**: adaptive mechanisms engage correctly under stiff or unstable conditions

Tests de-prioritize:
- Trivial smoke tests (though basic API availability is checked)
- Redundant coverage of the same numerical pathway
- Exact floating-point agreement
