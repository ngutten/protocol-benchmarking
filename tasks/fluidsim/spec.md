# FluidSim: 2D Incompressible Fluid Dynamics Engine

## Overview

Implement a 2D incompressible fluid dynamics simulator that communicates via a
JSON protocol over stdin/stdout. The engine solves the incompressible Navier-Stokes
equations (and the simpler Stokes subset) on rectangular grids, supporting various
boundary conditions, immersed boundary obstacles, flow diagnostics, and multigrid
acceleration.

## External Interface

The engine MUST be usable as a subprocess that communicates via **stdin/stdout**.
Commands are sent as JSON objects, one per line. Responses are returned as JSON
objects, one per line.

```
> {"command": "create", "grid": {"nx": 32, "ny": 32, "lx": 1.0, "ly": 1.0}, "fluid": {"viscosity": 0.01}}
{"status": "ok"}

> {"command": "set_boundary", "boundary": "top", "type": "velocity", "value": [1.0, 0.0]}
{"status": "ok"}

> {"command": "solve_steady", "tolerance": 1e-6, "max_iterations": 10000}
{"converged": true, "iterations": 342, "residual": 8.7e-7}

> {"command": "get_value", "field": "velocity_x", "point": [0.5, 0.5]}
{"value": 0.0312}

> {"command": "invalid_command"}
{"error": "Unknown command: invalid_command"}
```

### Response Format

- **Success with no data:** `{"status": "ok"}`
- **Success with data:** JSON object with result fields (command-specific)
- **Errors:** `{"error": "description"}`

## Commands

### Core Commands (Stage 1)

| Command | Parameters | Response |
|---------|-----------|----------|
| `create` | `grid: {nx, ny, lx, ly}`, `fluid: {viscosity}`, optional `force: [fx, fy]` | `{"status": "ok"}` |
| `set_boundary` | `boundary` (top/bottom/left/right), `type` (velocity/no_slip), `value` (for velocity type: [vx, vy]) | `{"status": "ok"}` |
| `solve_steady` | `tolerance`, `max_iterations` | `{"converged": bool, "iterations": int, "residual": float}` |
| `get_field` | `field` (velocity_x/velocity_y/pressure) | `{"shape": [ny, nx], "data": [[...]]}` |
| `get_value` | `field`, `point: [x, y]` | `{"value": float}` |
| `get_profile` | `field`, `line` (vertical/horizontal), `position`, `n_points` | `{"coordinates": [...], "values": [...]}` |
| `reset` | (none) | `{"status": "ok"}` |
| `status` | (none) | `{"grid": {nx, ny, lx, ly}, "time": float, "has_solution": bool, ...}` |

### Stage 2 Additions

| Command | Parameters | Response |
|---------|-----------|----------|
| `step` | `dt`, `steps` (default 1) | `{"time": float, "steps_completed": int}` |

- `get_field`, `get_value`, `get_profile` gain support for `vorticity` field.
- `solve_steady` now solves the full Navier-Stokes equations (not just Stokes).

### Stage 3 Additions

| Command | Parameters | Response |
|---------|-----------|----------|
| `load_config` | `path` (path to JSON config file) | `{"status": "ok"}` |
| `add_obstacle` | `type` (circle/rectangle), shape params | `{"obstacle_id": int}` |

- `set_boundary` gains new types: `inflow` (with `profile`: uniform/parabolic), `outflow`, `periodic` (with `paired_with`).

### Stage 4 Additions

| Command | Parameters | Response |
|---------|-----------|----------|
| `get_diagnostics` | (none) | `{"drag": float, "lift": float, ...}` |
| `get_diagnostic_history` | `diagnostic` (name) | `{"times": [...], "values": [...]}` |

- Config files gain a `diagnostics` section.

### Stage 5 Additions

| Command | Parameters | Response |
|---------|-----------|----------|
| `set_solver` | `type` (multigrid/default), `levels`, `cycle` (V/W), `pre_smooth`, `post_smooth` | `{"status": "ok"}` |

- Existing commands are unchanged; the solver choice is transparent.

## Physics

### Governing Equations

**Stokes equations** (Stage 1, no advection):
```
-ν∇²u + ∇p = f
∇·u = 0
```

**Navier-Stokes equations** (Stage 2+):
```
∂u/∂t + (u·∇)u = -∇p/ρ + ν∇²u + f
∇·u = 0
```

where `u` is velocity, `p` is pressure, `ν` is kinematic viscosity, `ρ` is density
(assumed 1), and `f` is an optional body force.

### Discretization

The choice of spatial discretization (finite difference, finite volume, staggered vs
collocated grid), incompressibility enforcement method (pressure Poisson, projection,
penalty, artificial compressibility), and iterative solver is left to the implementer.

## Error Handling

- Unknown command: `{"error": "Unknown command: name"}`
- Missing required parameter: `{"error": "Missing parameter: name"}`
- Invalid parameter value: `{"error": "Invalid value for parameter: details"}`
- No simulation created: `{"error": "No simulation created"}`
- No solution available: `{"error": "No solution available"}`
