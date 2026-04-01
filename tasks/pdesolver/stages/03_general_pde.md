# Stage 3: General Nonlinearities

## Goal

Generalize the solver so that the user can specify arbitrary nonlinear PDEs by providing the right-hand side as a callable expression involving the field, its spatial derivatives, other fields, coordinates, and user-defined parameters. The solver should handle reaction-diffusion systems and classical field theories like the XY model.

All Stage 1 and Stage 2 behavior must be preserved.

## Context

The previous stages hard-coded the diffusion and Poisson equations. A general-purpose PDE solver must allow the user to specify equations of the form:

    du/dt = F(u, grad(u), laplacian(u), x, y, t, ...)

where `F` can involve arbitrary combinations of the field, its spatial derivatives, spatial coordinates, and time. Nonlinear terms like `u * (1 - u)` (logistic growth) or `|grad(u)|^2` (gradient energy) must be expressible.

The XY model (or O(2) model) is a classical field theory where a 2D angle field `theta(x,y)` evolves to minimize the energy `E = integral (|grad(theta)|^2) dx dy`. Its relaxation dynamics are:

    d(theta)/dt = laplacian(theta)

but with the wrinkle that `theta` is an angular variable (periodic in `[0, 2*pi)`), and topological defects (vortices) emerge. This is a good test of general PDE capability because it combines the Laplacian with angular field handling.

## Requirements

### General Equation Specification

The library must allow the user to define a PDE by providing the right-hand side of `du/dt = ...` as a callable expression. This expression can reference:

- The field value itself (`u`)
- Spatial derivatives of the field: first-order partial derivatives (`du/dx`, `du/dy`), the Laplacian (`laplacian(u)` or `nabla^2 u`), and the gradient (`grad(u)`)
- Other fields defined in the simulation (by name)
- Spatial coordinates (`x`, `y`) and time (`t`)
- Standard mathematical functions (sin, cos, exp, sqrt, abs, etc.)
- User-defined parameters (constants like diffusion coefficient, reaction rate, etc.)

For vector fields, the expression should support divergence, curl, and the vector Laplacian.

The expression may be nonlinear in `u` and its derivatives. For example:

- Fisher-KPP equation: `du/dt = D * laplacian(u) + r * u * (1 - u)`
- Coupled predator-prey: `du/dt = D_u * laplacian(u) + u*(1-u) - u*v` and `dv/dt = D_v * laplacian(v) + u*v - m*v`

### XY Model Support

The combination of general equation specification and angular field handling should enable simulating the XY model. Specifically:

- A scalar field `theta` representing an angle, with values interpreted modulo `2*pi`
- Dynamics: `d(theta)/dt = laplacian(theta)` (or a variant with nonlinear terms)
- The solver should handle the angular wrapping correctly when computing finite differences (i.e., the difference between angles 0.1 and 6.2 should be about 0.18, not -6.1)

The library does not need a special "angular field" mode if the user can achieve correct behavior by providing appropriate nonlinear terms. But some mechanism must exist to get correct angular derivatives.

### User-Defined Parameters

The user must be able to define named parameters (e.g., `D = 0.1`, `r = 1.0`) and reference them in equation specifications. Parameters should be changeable between timesteps without rebuilding the entire simulation.

## Required API (New in Stage 3)

All Stage 1 and Stage 2 API remains unchanged. The following changes and additions apply.

### General equation via RHS callable

```python
def my_rhs(fields, operators, x, y, t, params):
    u = fields["u"]
    lap_u = operators["laplacian"]
    D = params["D"]
    r = params["r"]
    return D * lap_u + r * u * (1 - u)

sim.add_field("u", rhs=my_rhs, params={"D": 1.0, "r": 1.0})
```

When `rhs` is provided, it replaces the built-in `D * laplacian(u)` equation. The callable receives:

- **`fields`**: a dict mapping field names to their current 2D numpy arrays. For the field being updated, `fields["u"]` is its current values. For coupled systems, other fields are also available (e.g., `fields["v"]`).
- **`operators`**: a dict containing pre-computed spatial derivatives of the current field. At minimum it contains `"laplacian"` (the 2D Laplacian as a 2D array).
- **`x`, `y`**: 2D coordinate arrays (from meshgrid with `indexing="ij"`), shape `(nx, ny)`.
- **`t`**: current simulation time (float).
- **`params`**: the user-supplied parameter dict.

The callable must return a 2D numpy array of shape `(nx, ny)` representing `du/dt`.

### Coupled fields

Each field in a coupled system has its own `rhs` and `params`:

```python
def prey_rhs(fields, operators, x, y, t, params):
    u = fields["u"]
    v = fields["v"]
    lap_u = operators["laplacian"]
    return params["D_u"] * lap_u + u * (1 - u) - u * v

def pred_rhs(fields, operators, x, y, t, params):
    u = fields["u"]
    v = fields["v"]
    lap_v = operators["laplacian"]
    return params["D_v"] * lap_v + u * v - params["m"] * v

sim.add_field("u", rhs=prey_rhs, params={"D_u": 0.1})
sim.add_field("v", rhs=pred_rhs, params={"D_v": 0.05, "m": 0.3})
```

All fields see each other's values via the `fields` dict. The `operators` dict always contains the spatial derivatives of the field currently being evaluated (i.e., when evaluating the RHS for field `"u"`, `operators["laplacian"]` is the Laplacian of `u`).

### Angular fields (XY model)

```python
sim.add_field("theta", rhs=xy_rhs, angular=True)
```

When `angular=True`, the solver uses angular-aware finite differences: differences between angles are taken modulo 2*pi into `[-pi, pi)` before dividing by the grid spacing. This enables correct Laplacian computation for fields that wrap around `[0, 2*pi)`.

### Runtime parameter modification

```python
sim.set_parameter("D", 0.1)
```

Changes the value of a named parameter in the `params` dict. The change takes effect on the next timestep. The parameter name must match a key used in a field's `params` dict.

### Initial conditions from arrays

`set_initial_condition` also accepts a raw 2D numpy array (shape `(nx, ny)`) directly, in addition to callables:

```python
rng = np.random.default_rng(seed=12345)
ic_data = 0.01 * rng.standard_normal((101, 101))
sim.set_initial_condition("u", ic_data)
```
