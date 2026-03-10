# Stage 1: Stokes Flow

## Goal

Implement a 2D Stokes flow solver with a JSON-based stdin/stdout protocol. The engine
reads one JSON command per line from stdin and writes one JSON response per line to stdout.

## Requirements

### 1. Engine process

Create a program called `fluidsim.py` that reads JSON commands from stdin (one per line)
and writes JSON responses to stdout (one per line).

```
> {"command": "create", "grid": {"nx": 32, "ny": 32, "lx": 1.0, "ly": 1.0}, "fluid": {"viscosity": 0.01}}
{"status": "ok"}

> {"command": "set_boundary", "boundary": "top", "type": "velocity", "value": [1.0, 0.0]}
{"status": "ok"}

> {"command": "solve_steady", "tolerance": 1e-6, "max_iterations": 10000}
{"converged": true, "iterations": 342, "residual": 8.7e-7}
```

### 2. Commands

#### `create`
Initialize the simulation grid and fluid properties.

Parameters:
- `grid`: `{nx, ny, lx, ly}` — grid resolution and physical domain size
- `fluid`: `{viscosity}` — kinematic viscosity (ν)
- `force` (optional): `[fx, fy]` — constant body force (e.g., for pressure-driven channel flow)

Response: `{"status": "ok"}`

#### `set_boundary`
Set boundary conditions on a domain edge.

Parameters:
- `boundary`: one of `"top"`, `"bottom"`, `"left"`, `"right"`
- `type`: one of `"velocity"`, `"no_slip"`
- `value`: for `"velocity"` type, `[vx, vy]`; not needed for `"no_slip"` (equivalent to velocity [0,0])

Response: `{"status": "ok"}`

#### `solve_steady`
Solve the Stokes equations to steady state.

Parameters:
- `tolerance`: convergence tolerance for the residual
- `max_iterations`: maximum number of solver iterations

Response: `{"converged": bool, "iterations": int, "residual": float}`

The Stokes equations to solve (no advection term):
```
-ν∇²u + ∇p = f
∇·u = 0
```

#### `get_field`
Return a full 2D field as a nested array.

Parameters:
- `field`: one of `"velocity_x"`, `"velocity_y"`, `"pressure"`

Response: `{"shape": [ny, nx], "data": [[row0], [row1], ...]}`

The data array has shape [ny, nx], where row 0 corresponds to y=0 (bottom)
and row ny-1 corresponds to y=ly (top).

#### `get_value`
Return an interpolated field value at a specific point.

Parameters:
- `field`: one of `"velocity_x"`, `"velocity_y"`, `"pressure"`
- `point`: `[x, y]` — coordinates in physical space

Response: `{"value": float}`

Values should be interpolated (bilinear or better) from the grid data.

#### `get_profile`
Return field values along a line through the domain.

Parameters:
- `field`: one of `"velocity_x"`, `"velocity_y"`, `"pressure"`
- `line`: `"vertical"` (constant x) or `"horizontal"` (constant y)
- `position`: the x-coordinate (for vertical) or y-coordinate (for horizontal)
- `n_points`: number of sample points along the line

Response: `{"coordinates": [...], "values": [...]}`

For a vertical line, `coordinates` are y-values; for horizontal, x-values.

#### `reset`
Clear all simulation state (grid, solution, boundaries).

Response: `{"status": "ok"}`

#### `status`
Return current simulation status.

Response: `{"grid": {"nx": int, "ny": int, "lx": float, "ly": float}, "time": 0.0, "has_solution": bool}`

If no simulation has been created, return `{"error": "No simulation created"}`.

### 3. Error handling

- Unknown command: `{"error": "Unknown command: name"}`
- Missing required parameter: `{"error": "Missing parameter: name"}`
- Command before `create`: `{"error": "No simulation created"}`
- Request for solution before solving: `{"error": "No solution available"}`

### 4. Physics

The Stokes equations govern viscous flow without inertia (no advection):

```
-ν∇²u + ∇p = f
∇·u = 0
```

The discretization scheme (finite difference, finite volume, etc.), grid arrangement
(staggered, collocated), incompressibility enforcement method (pressure Poisson,
projection, penalty, etc.), and iterative solver are left to the implementer.

## Out of scope for this stage

- Time-dependent simulation (`step` command)
- Vorticity field
- Advection / Navier-Stokes
- Inflow/outflow/periodic boundary conditions
- Obstacles
- Diagnostics
- Multigrid solver
