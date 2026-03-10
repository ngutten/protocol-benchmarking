# Stage 5: Multigrid Solver

## Goal

Add a multigrid solver option that accelerates the pressure Poisson solve (or
equivalent linear system). The multigrid solver must be selectable via a command
and produce results matching the baseline solver to a given tolerance.

## Requirements

### 1. `set_solver` command

```json
{"command": "set_solver", "type": "multigrid", "levels": 4, "cycle": "V", "pre_smooth": 2, "post_smooth": 2}
```

Parameters:
- `type`: `"multigrid"` or `"default"` (revert to baseline solver)
- `levels`: number of multigrid levels (including the finest)
- `cycle`: `"V"` or `"W"` — cycle type
- `pre_smooth`: number of pre-smoothing iterations (default 2)
- `post_smooth`: number of post-smoothing iterations (default 2)

Response: `{"status": "ok"}`

### 2. Transparent integration

Once `set_solver` is called, subsequent `solve_steady` and `step` commands use the
multigrid solver for their internal linear solves. All other commands remain unchanged.
The user-facing behavior (fields, diagnostics, etc.) must be identical (within tolerance)
whether multigrid or default solver is used.

### 3. Multigrid components

The multigrid solver must implement:

- **Restriction operator**: transfer residuals from fine to coarse grid
- **Prolongation (interpolation) operator**: transfer corrections from coarse to fine grid
- **Smoother**: iterative relaxation at each level (e.g., Gauss-Seidel, Jacobi)
- **Coarsest level solve**: direct or heavily iterated solve at the coarsest level

The specific operators and smoother are left to the implementer.

### 4. Error handling

- Invalid cycle type: `{"error": "Invalid cycle type: name"}`
- Invalid number of levels: `{"error": "Invalid number of levels"}`
- `set_solver` before `create`: `{"error": "No simulation created"}`

### 5. Backward compatibility

Calling `set_solver` with `type: "default"` must restore the original solver behavior.
All existing tests must pass regardless of solver choice.

## Restructuring test

Multigrid requires a multi-level grid hierarchy — restriction and prolongation between
grids of different resolutions. If the Stage 1-4 implementation has tightly coupled the
solver to a single grid representation, adding multigrid requires significant
restructuring. Well-designed grid abstractions make this stage manageable.

## Out of scope

- Full multigrid (FMG) — only standard V/W cycles required
- Algebraic multigrid (AMG) — geometric multigrid only
- Adaptive mesh refinement
