# Stage 1: 2D Diffusion on a Square Grid

## Goal

Build a Python library that solves the two-dimensional time-dependent diffusion (heat) equation on a uniform square grid, with support for Dirichlet, Neumann, Robin, and periodic boundary conditions.

## Context

The diffusion equation is:

    du/dt = D * laplacian(u)

where `u(x, y, t)` is a scalar field, `D` is the diffusion coefficient, and the Laplacian is the standard 2D operator (d^2u/dx^2 + d^2u/dy^2). The solver discretizes this on a uniform Cartesian grid and advances in time using explicit or implicit stepping.

## Requirements

### Grid and Domain

The library must support creating a simulation on a rectangular domain `[x_min, x_max] x [y_min, y_max]` discretized into an `Nx x Ny` uniform grid. The user specifies the physical extent and grid resolution. Grid points should be cell-centered or node-centered (either is acceptable, but the choice must be consistent).

### Initial Conditions

The user must be able to set the initial state of the field by providing a callable `f(x, y)` that returns the field value at each grid point. The library evaluates this function over the grid to populate the initial field. Alternatively, the user may directly supply a 2D array of values matching the grid dimensions.

### Boundary Conditions

Four types of boundary conditions must be supported. Each can be set independently on each of the four edges (left, right, top, bottom), and each is specified with a callable that can depend on position along the boundary and on time:

1. **Dirichlet**: the field value is prescribed on the boundary. `u(boundary) = g(s, t)` where `s` is the coordinate along the edge and `t` is time.

2. **Neumann**: the normal derivative is prescribed on the boundary. `du/dn(boundary) = g(s, t)`. The sign convention is that `n` points outward.

3. **Robin**: a linear combination of the field and its normal derivative is prescribed. `a * u + b * du/dn = g(s, t)` on the boundary, with user-specified constants `a`, `b` and function `g`.

4. **Periodic**: The field wraps around on the identified edges, with the boundary behaving no differently from some place in the middle of the domain. Setting periodic on the left edge automatically makes the right edge periodic too (and similarly for top/bottom). When periodic is set, any BC function on the paired opposite edge is ignored.

If no boundary condition is explicitly set for an edge, the default should be homogeneous Dirichlet (u = 0).

### Time Stepping

The library must provide a way to advance the simulation by a specified time increment or by a specified number of steps at a given dt. The user should be able to:

- Step forward by a given dt (one step)
- Step forward by N steps of a given dt
- Step forward to reach a given target time

The time-stepping scheme should at minimum support forward Euler (explicit).

### Field Access

After stepping, the user must be able to read back:

- The current field values as a 2D NumPy array
- The current simulation time
- The grid coordinates (arrays of x and y values)

### Diffusion Coefficient

The diffusion coefficient `D` must be settable as a non-negative scalar, and `D = 0` should be valid that does not cause any infinities. 

## Required API

The library must be importable as `import pdesolver` and expose the following API.

### Simulation object

```python
sim = pdesolver.Simulation(x_range=(x_min, x_max), y_range=(y_min, y_max), nx=101, ny=101)
```

All parameters are keyword arguments. `x_range` and `y_range` are `(min, max)` tuples defining the physical domain. `nx` and `ny` are the number of grid points in each direction. The grid must support non-square configurations (e.g., `nx=51, ny=101`).

### Adding a diffusion field

```python
sim.add_field("u", D=1.0)
```

The first argument is a string name for the field. `D` is the diffusion coefficient (scalar).

### Initial conditions

```python
# From a callable f(x, y) -> array:
sim.set_initial_condition("u", lambda x, y: np.sin(np.pi * x) * np.sin(np.pi * y))

# From a 2D numpy array matching the grid shape (nx, ny):
sim.set_initial_condition("u", data_array)
```

When a callable is provided, the library evaluates it with 2D arrays `x` and `y` (shaped via `meshgrid` with `indexing="ij"`) and uses the result.

### Boundary conditions

```python
sim.set_bc("field_name", "edge", "bc_type", **params)
```

**Edge names**: `"left"`, `"right"`, `"top"`, `"bottom"`, or `"all"` (applies to all four edges).

**Boundary condition types and their keyword arguments**:

- **Dirichlet**: `sim.set_bc("u", "left", "dirichlet", value=0.0)`
  - `value` can be a scalar or a callable `value(s, t)` where `s` is the coordinate along the edge and `t` is the current time. Example: `value=lambda s, t: np.sin(2 * np.pi * t) * np.ones_like(s)`

- **Neumann**: `sim.set_bc("u", "all", "neumann", flux=0.0)`
  - `flux` can be a scalar or a callable `flux(s, t)`.

- **Robin**: `sim.set_bc("u", "all", "robin", a=1.0, b=0.5, g=0.0)`
  - Implements `a * u + b * du/dn = g` on the boundary. `a`, `b`, `g` are scalars.

- **Periodic**: `sim.set_bc("u", "all", "periodic")`
  - No additional keyword arguments. Setting periodic on one edge automatically pairs it with the opposite edge.

### Time stepping

```python
# Single step:
sim.step(dt=0.001)

# Multiple steps:
sim.step(dt=0.001, n_steps=100)

# Advance to a target time:
sim.run_until(target_time, dt=0.001)
```

`step` with `n_steps` must produce identical results to calling `step` that many times in a loop. `run_until` advances the simulation to the specified target time using steps of size `dt`.

### Field access

```python
u = sim.get_field("u")       # Returns a 2D numpy array of shape (nx, ny)
x, y = sim.coordinates()     # Returns two 1D numpy arrays of lengths nx and ny
t = sim.time                  # Current simulation time (float, starts at 0.0)
```

`get_field` returns the current field values as a 2D array where the first axis is x and the second axis is y: `u[i, j]` is the value at `(x[i], y[j])`. This corresponds to `np.meshgrid(x, y, indexing="ij")`. The shape must be `(nx, ny)` for all grid configurations, including non-square grids. Reading the field must not alter the simulation state. `coordinates()` returns 1D arrays of the grid point positions in x and y.

### Edge orientation

- `"left"` is the edge at `x = x_min` (first column, `u[0, :]`)
- `"right"` is the edge at `x = x_max` (last column, `u[-1, :]`)
- `"bottom"` is the edge at `y = y_min` (first row, `u[:, 0]`)
- `"top"` is the edge at `y = y_max` (last row, `u[:, -1]`)
