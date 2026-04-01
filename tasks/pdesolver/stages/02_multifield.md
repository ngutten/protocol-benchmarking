# Stage 2: Multiple Fields, Static Fields, and Poisson

## Goal

Extend the solver to support multiple interacting fields on the same grid, including vector-valued fields. Support static (non-evolving) fields that serve as source terms or parameters for other fields. Support one-shot Poisson solves. Implement a numerical stability monitor that detects divergence and adaptively reduces the timestep.

All Stage 1 behavior must be preserved.

## Context

Many physical systems involve multiple coupled fields. An electrostatics problem has a charge density field and an electric potential field; the charge density is given data, and the potential satisfies the Poisson equation sourced by the charge. Reaction-diffusion systems couple multiple scalar fields through nonlinear source terms.

Rather than introducing special-purpose APIs for each equation type, the solver should support these naturally through its field system. A field with no equation at all is static data that can be used as a source term or spatially-varying coefficient. The Poisson equation can be solved as a one-shot operation: given a source field and boundary conditions, solve for the unknown field.

Numerical instability is a practical reality of explicit time-stepping. When the CFL condition or diffusive stability limit is violated, the solution blows up exponentially. A production solver should detect this and recover gracefully.

## Requirements

### Multiple Fields

The simulation must support defining and evolving multiple named fields on the same grid. Each field can have its own equation, boundary conditions, and initial conditions. Fields should be able to reference each other's values (e.g., a source term in one equation that depends on another field).

### Static Fields

A field may be defined with no governing equation. It simply holds data set by the user via initial conditions or direct array assignment. Static fields are useful as source terms, spatially-varying coefficients, or externally imposed data. The user should be able to update a static field's values between timesteps.

### Vector Fields

A vector field is a field with two components (for 2D), representing quantities like velocity. The library must support creating vector fields, setting initial/boundary conditions for each component, and evolving them. Differential operators on vector fields should work naturally (e.g., divergence of a vector field yields a scalar, gradient of a scalar yields a vector).

### Poisson Equation (One-Shot Solve)

The library must support solving the Poisson equation as a one-shot operation:

    laplacian(phi) = f

where `f` is a known source (a static field, an array, or a callable). The user provides the source, boundary conditions for `phi`, and requests the solve. The solver iterates (e.g., Jacobi, Gauss-Seidel, conjugate gradient) or uses a direct method until the residual is below a user-specified tolerance, then returns the result.

This is a standalone operation, not embedded in the time-stepping loop. The user calls it explicitly when they want a Poisson solve. There is no automatic per-timestep re-solving of elliptic sub-problems.

### Numerical Stability Monitor

When evolving a time-dependent equation, the solver must monitor the field for signs of numerical instability. Specifically:

- After each step (or every few steps), check whether the field values are growing unreasonably (e.g., maximum absolute value exceeds some multiple of the initial maximum, or NaN/Inf appear).
- If instability is detected, the solver must: (a) restore the field to its state before the unstable step(s), (b) reduce the timestep by a factor (e.g., halve it), and (c) retry from the restored state.
- The solver should report (via a log, callback, or return value) when adaptive reduction occurs.
- If the timestep has been reduced below some minimum threshold and instability persists, the solver should raise an error rather than looping forever.

## Required API (New in Stage 2)

All Stage 1 API remains unchanged. The following methods are added.

### Static fields

```python
# Create a static (non-evolving) field from a 2D numpy array:
sim.add_static_field("rho", data=array_2d)

# Update a static field's values between timesteps:
sim.update_static_field("rho", data=new_array_2d)
```

`data` is a 2D numpy array matching the grid shape `(nx, ny)`.

### Fields with a source term

```python
sim.add_field("u", D=1.0, source="source_field_name")
```

The `source` keyword names a static field whose values are added as a forcing term to the diffusion equation: `du/dt = D * laplacian(u) + source`.

### Fields without a diffusion coefficient

```python
sim.add_field("phi")
```

A field added without `D` has no time-evolution equation. It can be used as the target of a Poisson solve.

### Poisson solve

```python
sim.poisson_solve("phi", source="rho", tol=1e-8)
```

Solves `laplacian(phi) = rho` as a one-shot operation. `"phi"` is the target field name, `source` is the name of a static field (or any field holding the source data), and `tol` is the convergence tolerance. Boundary conditions for `phi` must be set beforehand via `set_bc`.

### Vector fields

```python
# Create a vector field from two 2D component arrays:
sim.add_vector_field("v", data_x=vx_array, data_y=vy_array)

# Compute divergence (returns a 2D numpy array):
div = sim.divergence("v")

# Compute scalar curl in 2D (returns a 2D numpy array):
curl_val = sim.curl("v")
```

`data_x` and `data_y` are 2D numpy arrays of shape `(nx, ny)` for the x- and y-components of the vector field.

### Stability monitor

The stability monitor is automatic and requires no additional API. When `step` or `run_until` is called with a `dt` that causes numerical instability, the solver must detect it, restore the field to its pre-step state, reduce `dt`, and retry. The final solution must be finite and accurate.
