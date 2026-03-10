# Stage 2: Navier-Stokes

## Goal

Extend the Stokes solver to handle the full incompressible Navier-Stokes equations,
including time-dependent simulation and vorticity computation.

## Requirements

### 1. Advection term

The solver must now include the nonlinear advection term:

```
∂u/∂t + (u·∇)u = -∇p + ν∇²u + f
∇·u = 0
```

This changes the character of the problem fundamentally. The solver must handle
Reynolds numbers up to Re = 1000 (based on characteristic velocity and length scale).

### 2. `step` command

Add a new command for time-dependent simulation:

```json
{"command": "step", "dt": 0.001, "steps": 100}
```

Parameters:
- `dt`: time step size
- `steps` (optional, default 1): number of steps to take

Response: `{"time": float, "steps_completed": int}`

The engine tracks the current simulation time. Each `step` advances the solution
by `steps * dt` time units.

### 3. `solve_steady` for Navier-Stokes

`solve_steady` must now solve the full Navier-Stokes equations to steady state
(not just Stokes). The method (pseudo-time stepping, Newton iteration, etc.) is
left to the implementer.

Parameters remain the same: `tolerance`, `max_iterations`.

### 4. Vorticity field

The `get_field`, `get_value`, and `get_profile` commands must now also accept
`"vorticity"` as a valid field name. Vorticity in 2D is the scalar:

```
ω = ∂v/∂x - ∂u/∂y
```

### 5. Backward compatibility

All Stage 1 commands must continue to work exactly as before. A simulation created
without calling `step` should behave identically to Stage 1 (Stokes-like behavior
is acceptable for solve_steady when Re is very low).

## Why this is an implicit invalidation

Adding the advection term requires modifying the core solver loop. If the Stage 1
implementation has the solver tightly coupled to the Stokes equations, this stage
requires restructuring. The `step` command also requires adding time state management
that didn't exist before.

## Out of scope

- Complex boundary conditions (inflow/outflow/periodic)
- Obstacles
- Diagnostics
- Multigrid
