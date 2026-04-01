# Test Specifications for Reference Code

Each test below specifies the exact parameters needed to produce reference output. Tests are grouped by stage. Tests that only check a property (conservation, monotonicity, error ratio) without comparing to a reference field are listed separately at the end of each stage.

All spatial coordinates are in physical units. All grids are uniform and node-centered unless stated otherwise. Where a random seed is needed, use `numpy.random.default_rng(seed)` with the specified seed.

Reference outputs should be saved as numpy `.npz` files. Each file should contain at minimum the field array(s) at the specified snapshot times, plus the x and y coordinate arrays.

Reference data file names match the test IDs (e.g., REF-1.1 → `ref_1_1.npz`, REF-4.8 → `ref_4_8.npz`).

---

## Stage 1: Diffusion

### REF-1.1: Gaussian blob diffusion

| Parameter | Value |
|-----------|-------|
| Domain | [0, 10] x [0, 10] |
| Grid | 101 x 101 |
| D | 1.0 |
| IC | `u(x,y) = exp(-((x-5)^2 + (y-5)^2) / 0.5)` |
| BC | Dirichlet u=0 on all edges |
| dt | 0.001 |
| Stepping | Forward Euler |

**Snapshots**: field at t = 0.1, 0.3, 0.5

**Notes**: The blob spreads and decays. Domain is large enough relative to the blob that boundary effects are mild but present by t=0.5.

---

### REF-1.2: Steady-state Laplace

| Parameter | Value |
|-----------|-------|
| Domain | [0, 1] x [0, 1] |
| Grid | 101 x 101 |
| D | 1.0 |
| IC | `u(x,y) = 0` |
| BC | Dirichlet: u=1 on top (y=1), u=0 on left, right, bottom |
| dt | 2e-5 |
| Stepping | Forward Euler |

**Snapshots**: field at t = 0.5, 1.0, and "converged" (run until max absolute change per step < 1e-8, or t = 5.0, whichever comes first)

**Notes**: On a 101x101 grid with dx=0.01 and D=1.0, the Forward Euler stability limit is dt_max = dx²/(4D) = 2.5e-5. The timestep dt=2e-5 is chosen to stay safely below this limit. Converged solution is the Laplace equation solution. Analytical series solution available:

    u(x,y) = sum_{n=1,3,5,...} (4/(n*pi)) * sin(n*pi*x) * sinh(n*pi*y) / sinh(n*pi)

Reference code should produce both the time-stepped output and the analytical series (truncated at n=99) for cross-validation.

---

### REF-1.3: Robin cooling

| Parameter | Value |
|-----------|-------|
| Domain | [0, 1] x [0, 1] |
| Grid | 101 x 101 |
| D | 1.0 |
| IC | `u(x,y) = 1.0` (uniform) |
| BC | Robin on all edges: `a=1.0, b=0.5, g=0` (i.e., `u + 0.5 * du/dn = 0`) |
| dt | 2e-5 |
| Stepping | Forward Euler |

**Snapshots**: field at t = 0.01, 0.05, 0.1

**Notes**: On a 101x101 grid with dx=0.01 and D=1.0, dt must be below the stability limit of 2.5e-5. Models convective cooling from a uniform initial temperature. The field should cool from the boundaries inward, remaining symmetric about both axes.

---

### REF-1.4: Periodic sinusoidal

| Parameter | Value |
|-----------|-------|
| Domain | [0, 2*pi] x [0, 2*pi] |
| Grid | 101 x 101 |
| D | 0.1 |
| IC | `u(x,y) = sin(x) + 0.5*cos(2*y)` |
| BC | Periodic in both x and y |
| dt | 0.003 |
| Stepping | Forward Euler |

**Snapshots**: field at t = 0.5, 1.0, 2.0

**Notes**: Has an exact analytical solution:

    u(x,y,t) = sin(x)*exp(-D*t) + 0.5*cos(2y)*exp(-4*D*t)

Reference code should produce both the time-stepped output and the analytical solution for cross-validation. The cos(2y) mode decays 4x faster than the sin(x) mode. The timestep dt=0.003 is chosen for spectral stability: with k_max ~50, D=0.1, the spectral stability limit is approximately dt_max = 2/(D * 2 * k_max²) ≈ 0.004.

---

### REF-1.5: Time-dependent Dirichlet

| Parameter | Value |
|-----------|-------|
| Domain | [0, 1] x [0, 1] |
| Grid | 101 x 101 |
| D | 1.0 |
| IC | `u(x,y) = 0` |
| BC | Left edge (x=0): Dirichlet `g(y, t) = sin(2*pi*t)`. Other three edges: Dirichlet u=0. |
| dt | 2e-5 |
| Stepping | Forward Euler |

**Snapshots**: field at t = 0.1, 0.25, 0.5

**Notes**: On a 101x101 grid with dx=0.01 and D=1.0, dt must be below the stability limit of 2.5e-5. The oscillating left boundary drives a diffusive wave into the domain. Save the boundary values at the left edge at each snapshot time to verify the BC is being applied.

---

### REF-1.6: Grid convergence (coarse)

| Parameter | Value |
|-----------|-------|
| Domain | [0, 1] x [0, 1] |
| Grid | **51 x 51** |
| D | 1.0 |
| IC | `u(x,y) = sin(pi*x) * sin(pi*y)` |
| BC | Dirichlet u=0 on all edges |
| dt | 0.2 * dx^2 / D (where dx = 1/50) = 8e-5 |
| Stepping | Forward Euler |

**Snapshots**: field at t = 0.05

**Notes**: Analytical solution: `u(x,y,t) = sin(pi*x)*sin(pi*y)*exp(-2*pi^2*D*t)`. Compute L2 error against analytical solution at t=0.05.

### REF-1.6b: Grid convergence (fine)

Same as REF-1.6 but:

| Parameter | Value |
|-----------|-------|
| Grid | **101 x 101** |
| dt | 0.2 * dx^2 / D (where dx = 1/100) = 2e-5 |

**Notes**: Error should be roughly 4x smaller than the 51x51 case (second-order convergence).

---

### Property-only tests (Stage 1, no reference needed)

**PROP-1.1: Neumann conservation**
- Domain: [0, 1] x [0, 1], Grid: 101x101, D=1.0
- IC: `u(x,y) = sin(2*pi*x) * cos(pi*y) + 1.5`
- BC: Neumann du/dn=0 on all edges
- dt=2e-5, Forward Euler, run to t=0.1 (dt must stay below stability limit of 2.5e-5)
- Check: `integral(u) dx dy` at t=0, 0.01, 0.05, 0.1 should be equal within 1e-6 relative tolerance

**PROP-1.2: Energy dissipation**
- Same setup as REF-1.1 (Gaussian blob with Dirichlet)
- Compute `integral(u^2) dx dy` at t=0, 0.05, 0.1, 0.2, 0.3, 0.5
- Check: strictly monotonically decreasing

---

## Stage 2: Multiple Fields

### REF-2.1: Two-field diffusion

Two independent scalar fields on the same grid, diffusing at different rates.

| Parameter | Value |
|-----------|-------|
| Domain | [0, 1] x [0, 1] |
| Grid | 101 x 101 |
| Field `a` | D=1.0, IC: `sin(pi*x)*sin(pi*y)`, BC: Dirichlet u=0 all edges |
| Field `b` | D=0.1, IC: `sin(pi*x)*sin(pi*y)`, BC: Dirichlet u=0 all edges |
| dt | 2e-5 |
| Stepping | Forward Euler |

**Snapshots**: both fields at t = 0.05, 0.1

**Notes**: On a 101x101 grid with dx=0.01 and D_max=1.0, dt must be below the stability limit of 2.5e-5. Fields should not interact. Field `a` decays 10x faster than field `b`. Each should match its independent single-field reference (and the analytical solution `sin(pi*x)*sin(pi*y)*exp(-2*pi^2*D*t)`).

---

### REF-2.2: Poisson via static source field

| Parameter | Value |
|-----------|-------|
| Domain | [0, 1] x [0, 1] |
| Grid | 101 x 101 |
| Field `rho` | Static (no equation). Values: `rho(x,y) = -2*pi^2 * sin(pi*x) * sin(pi*y)` |
| Field `phi` | One-shot Poisson solve: `laplacian(phi) = rho`. BC: Dirichlet phi=0 all edges. Convergence tolerance: 1e-8. |

**Snapshots**: `phi` after the solve completes

**Notes**: Analytical solution is `phi(x,y) = sin(pi*x)*sin(pi*y)`. This is a single solve, not embedded in a time-stepping loop. The reference should also save the final residual `max|laplacian(phi) - rho|`.

---

### REF-2.3: Stability monitor — reference run

This produces the "correct answer" that the stability-monitored run should match.

| Parameter | Value |
|-----------|-------|
| Domain | [0, 1] x [0, 1] |
| Grid | 101 x 101 |
| D | 1.0 |
| IC | `u(x,y) = sin(pi*x) * sin(2*pi*y)` |
| BC | Dirichlet u=0 on all edges |
| dt | 1e-5 (a conservatively stable dt) |
| Stepping | Forward Euler |

**Snapshots**: field at t = 0.01, 0.02

**Notes**: The test code will attempt this same problem with dt=0.01 (wildly unstable for Euler on a 101x101 grid where the stability limit is ~5e-5). The stability monitor should reduce dt automatically and produce a result matching this reference. A second test will use dt=0.05 (even more extreme) to test deep recovery.

---

### REF-2.4: Static field update

| Parameter | Value |
|-----------|-------|
| Domain | [0, 1] x [0, 1] |
| Grid | 101 x 101 |
| Field `source` | Static. Phase 1 values: `source(x,y) = 5.0 * sin(pi*x) * sin(pi*y)`. Phase 2 values: `source(x,y) = 5.0 * sin(2*pi*x) * sin(2*pi*y)`. |
| Field `u` | Equation: `du/dt = laplacian(u) + source`. IC: `u(x,y) = 0`. BC: Dirichlet u=0 all edges. D=1.0. |
| dt | 2e-5 |
| Stepping | Forward Euler |

**Schedule**:
1. Phase 1: set `source` to phase 1 values, step 500 timesteps (t=0 to t=0.01)
2. Phase 2: update `source` to phase 2 values, step 500 more timesteps (t=0.01 to t=0.02)

**Snapshots**: `u` at t = 0.01 (end of phase 1) and t = 0.02 (end of phase 2)

**Notes**: On a 101x101 grid with dx=0.01 and D=1.0, dt must be below the stability limit of 2.5e-5. The source field drives `u` upward; changing the source pattern should visibly change the spatial structure of `u`'s growth. No Poisson solve involved — this purely tests the static field update mechanism with a time-dependent field that reads from it.

---

### Property-only tests (Stage 2, no reference needed)

**PROP-2.1: Vector field divergence and curl**
- Domain: [0, 2*pi] x [0, 2*pi], Grid: 101x101
- Vector field: `v = (sin(x)*cos(y), -cos(x)*sin(y))`
- Analytical divergence: `cos(x)*cos(y) - cos(x)*cos(y) = 0` everywhere
- Analytical scalar curl (2D): `sin(x)*sin(y) - (-sin(x)*sin(y)) = 2*sin(x)*sin(y)`
- Check computed values against analytical within 1% at interior points

---

## Stage 3: General PDE

### REF-3.1: Fisher-KPP traveling wave

| Parameter | Value |
|-----------|-------|
| Domain | [0, 40] x [0, 1] (elongated channel) |
| Grid | 401 x 11 |
| D | 1.0 |
| r | 1.0 |
| Equation | `du/dt = D * laplacian(u) + r * u * (1 - u)` |
| IC | `u(x,y) = 1.0 if x < 5.0 else 0.0` (step function) |
| BC | Neumann du/dn=0 on all edges |
| dt | 0.002 |
| Stepping | Forward Euler |

**Snapshots**: field at t = 5.0, 10.0, 15.0

**Notes**: On a 401x11 grid with dx=dy=0.1 and D=1.0, the stability limit is dt_max = dx²/(4D) = 0.0025; dt=0.002 is used for safety. A rightward-propagating front should develop with asymptotic speed `2*sqrt(D*r) = 2.0`. The grid is quasi-1D (narrow in y) to simplify comparison. By t=15, the front should be well-developed and have traveled roughly 30 units. Save the midline profile `u(x, y=0.5, t)` at each snapshot for 1D comparison.

---

### REF-3.3: Coupled predator-prey

| Parameter | Value |
|-----------|-------|
| Domain | [0, 10] x [0, 10] |
| Grid | 101 x 101 |
| D_u | 0.1 |
| D_v | 0.05 |
| m | 0.3 |
| Field `u` equation | `du/dt = D_u * laplacian(u) + u*(1-u) - u*v` |
| Field `v` equation | `dv/dt = D_v * laplacian(v) + u*v - m*v` |
| IC `u` | `0.8 + 0.1*sin(pi*x/10)*sin(pi*y/10)` |
| IC `v` | `0.2 + 0.1*cos(pi*x/10)*cos(pi*y/10)` |
| BC | Neumann du/dn=0, dv/dn=0 on all edges |
| dt | 0.005 |
| Stepping | Forward Euler |

**Snapshots**: both fields at t = 1.0, 5.0, 10.0

---

### REF-3.4: XY model vortex annihilation

| Parameter | Value |
|-----------|-------|
| Domain | [0, 10] x [0, 10] |
| Grid | 201 x 201 |
| Equation | `d(theta)/dt = laplacian(theta)` with angular-aware finite differences |
| IC | See below |
| BC | Periodic in both x and y |
| dt | 5e-4 |
| Stepping | Forward Euler |

**Initial condition**: a vortex-antivortex pair.

```python
# Vortex at (3.5, 5.0), antivortex at (6.5, 5.0)
theta(x, y) = arctan2(y - 5.0, x - 3.5) - arctan2(y - 5.0, x - 6.5)
```

The result should be taken modulo 2*pi into [0, 2*pi).

**Snapshots**: field at t = 1.0, 5.0, 10.0, 20.0

**Also save** at each snapshot:
- Total energy: `E = 0.5 * integral(|grad(theta)|^2) dx dy` (using angular-aware gradient)
- Winding numbers around two small loops: one centered at (3.5, 5.0) and one at (6.5, 5.0), each of radius 1.0. Computed as `(1/2*pi) * line_integral(grad(theta) . dl)`.

**Notes**: On a 201x201 grid with dx ≈ 0.0498, the stability limit is dt_max ≈ dx²/4 ≈ 6.2e-4; dt=5e-4 is used for safety. The vortex and antivortex should attract each other and annihilate. Energy should decrease monotonically. Initially the winding numbers are +1 and -1; after annihilation both become 0. Angular-aware derivatives mean: `d(theta)/dx` at a point should be the angular difference `(theta_{i+1} - theta_i) mod_symmetric 2*pi` divided by dx, where `mod_symmetric` maps into `[-pi, pi)`.

---

### REF-3.5: Parameter modification

| Parameter | Value |
|-----------|-------|
| Domain | [0, 1] x [0, 1] |
| Grid | 101 x 101 |
| Equation | `du/dt = D * laplacian(u)` with named parameter D |
| IC | `u(x,y) = sin(pi*x)*sin(pi*y)` |
| BC | Dirichlet u=0 all edges |
| dt | 2e-5 |
| Stepping | Forward Euler |

**Schedule**:
1. Phase 1: D = 1.0, step 1000 timesteps (to t=0.02)
2. Phase 2: D = 0.1, step 4000 timesteps (to t=0.10)

**Snapshots**: field at t = 0.02 (end of phase 1) and t = 0.10 (end of phase 2)

**Notes**: On a 101x101 grid with dx=0.01 and D_max=1.0, dt must be below the stability limit of 2.5e-5. Analytical solution exists piecewise. In phase 1: `sin(pi*x)*sin(pi*y)*exp(-2*pi^2*1.0*t)`. In phase 2 (starting from phase 1 endpoint): the same eigenmode but with the slower decay rate. Verify reference matches analytical.

---

Stage 3 has no property-only tests; all tests compare against reference solutions.

---

## Stage 4: Smart Numerics

### REF-4.1: Upwind advection of square pulse

| Parameter | Value |
|-----------|-------|
| Domain | [0, 10] x [0, 2] |
| Grid | 201 x 41 |
| Velocity | Uniform `v = (1.0, 0.0)` (static vector field or constant) |
| Equation | `du/dt = -v . grad(u)` (pure advection) |
| IC | `u(x,y) = 1.0 if 2.0 <= x <= 3.0 else 0.0` (square pulse) |
| BC | Periodic in x, Neumann in y |
| dt | 0.01 |
| Stepping | Forward Euler |

**Snapshots**: field at t = 2.0, 4.0

**Notes**: The pulse should translate rightward at speed 1. With upwinding, the pulse will diffuse numerically but should not ring. Save both:
1. The upwinded result (solver's automatic choice)
2. A forced central-difference result for comparison (to show ringing)

The midline profile `u(x, y=1.0, t)` is the key comparison quantity.

---

### REF-4.2: Advection-diffusion

| Parameter | Value |
|-----------|-------|
| Domain | [0, 10] x [0, 10] |
| Grid | 101 x 101 |
| Equation | `du/dt = -v . grad(u) + D * laplacian(u)` |
| D | 0.1 |
| Velocity | `v = (1.0, 0.5)` (uniform, static) |
| IC | `u(x,y) = exp(-((x-3)^2 + (y-3)^2) / 0.5)` (Gaussian blob) |
| BC | Periodic in both x and y |
| dt | 0.003 |
| Stepping | Forward Euler |

**Snapshots**: field at t = 1.0, 3.0

**Notes**: With a spectral Laplacian on a 101x101 periodic grid, the diffusive stability limit is approximately dt_max ≈ 2/(D * 2 * k_max²) ≈ 0.004 for D=0.1 and k_max ~50. The CFL condition (dt < dx/|v|) is more permissive at ~0.099. dt=0.003 is chosen for safety. The blob should translate in the direction (1.0, 0.5) while spreading due to diffusion.

---

### REF-4.3: Biharmonic (Cahn-Hilliard-like)

| Parameter | Value |
|-----------|-------|
| Domain | [0, 2*pi] x [0, 2*pi] |
| Grid | 128 x 128 |
| kappa | 0.0001 |
| Equation | `du/dt = -kappa * nabla^4(u) + u - u^3` |
| IC | `u(x,y) = 0.01 * rng.standard_normal((128, 128))` with `rng = numpy.random.default_rng(seed=54321)` |
| BC | Periodic in both x and y |
| dt | 1e-7 |
| Stepping | Forward Euler |

**Snapshots**: field at t = 1e-4, 5e-4, 1e-3

**Notes**: Periodic domain with power-of-2 grid for efficient FFT. The biharmonic `nabla^4` should be computed spectrally (multiply by `(kx^2 + ky^2)^2` in Fourier space). This is stiff due to the biharmonic; small dt is necessary. Phase separation should begin by t=1e-3.

Also test spectral operator accuracy separately: apply `nabla^4` to the field `u(x,y) = cos(2x)*cos(3y)` on the same grid. Analytical result: `nabla^4(cos(2x)*cos(3y)) = (4+9)^2 * cos(2x)*cos(3y) = 169 * cos(2x)*cos(3y)`. The spectral method should reproduce this to machine precision on a periodic domain.

---

### REF-4.4: Triharmonic evolution

| Parameter | Value |
|-----------|-------|
| Domain | [0, 2*pi] x [0, 2*pi] |
| Grid | 128 x 128 |
| Equation | `du/dt = -nabla^6(u)` |
| IC | `u(x,y) = sin(x)*sin(y)` |
| BC | Periodic in both x and y |
| dt | 1e-6 |
| Stepping | Exact spectral integration |

**Snapshots**: field at t = 1e-4, 5e-4

**Notes**: Forward Euler is **unconditionally unstable** for the triharmonic equation because high-k modes have k^6 growth rates that exceed any fixed timestep's stability region. The reference uses exact spectral integration: `u_hat(t+dt) = u_hat(t) * exp(-k^6 * dt)`, which is unconditionally stable. The eigenmode `sin(x)*sin(y)` under the `(k²)³` operator has eigenvalue `(1+1)^3 = 8`, so the analytical solution is `sin(x)*sin(y)*exp(-8*t)`. At t=1e-4 the field should have decayed by a factor of exp(-8e-4) ~ 0.9992. The spectral method should be exact for this single-mode field.

Also test spectral operator accuracy: apply `nabla^6` to `u(x,y) = cos(2x)*cos(3y)`. Analytical result: `nabla^6(cos(2x)*cos(3y)) = -(4+9)^3 * cos(2x)*cos(3y) = -2197 * cos(2x)*cos(3y)`. Should match to machine precision.

---

### REF-4.5: Swift-Hohenberg pattern formation

| Parameter | Value |
|-----------|-------|
| Domain | [0, 50] x [0, 50] |
| Grid | 256 x 256 |
| r | 0.3 |
| Equation | `du/dt = r*u - (1 + nabla^2)^2 * u - u^3` = `(r-1)*u - 2*nabla^2(u) - nabla^4(u) - u^3` |
| IC | `u(x,y) = 0.01 * rng.standard_normal((256, 256))` with `rng = numpy.random.default_rng(seed=99999)` |
| BC | Periodic in both x and y |
| dt | 0.05 |
| Stepping | IMEX (linear part exact in spectral space, nonlinear `-u^3` explicit) |

**Snapshots**: field at t = 10.0, 50.0, 200.0

**Notes**: The `-u^3` nonlinear saturation term is required for physical pattern formation; without it, linearly unstable modes grow exponentially forever. The IMEX scheme treats the linear part `(r - 1 + 2k² - k⁴)` exactly via `exp(L*dt)` in spectral space, and applies the nonlinear `-u³` term explicitly: `u_hat(t+dt) = exp(L*dt) * [u_hat(t) + dt * FFT(-u³(t))]`. Stripe or spot patterns with wavelength ~2*pi should emerge. The large domain allows many pattern wavelengths. Exact reproducibility requires the same random seed and the same stepping.

---

### REF-4.6: Time-stepping order verification

Use the same problem for all three integrators:

| Parameter | Value |
|-----------|-------|
| Domain | [0, 1] x [0, 1] |
| Grid | 51 x 51 |
| D | 1.0 |
| Equation | `du/dt = D * laplacian(u)` |
| IC | `u(x,y) = sin(pi*x) * sin(pi*y)` |
| BC | Dirichlet u=0 all edges |

Run six cases:

| Case | Method | dt |
|------|--------|----|
| 1 | Euler | 5e-5 |
| 2 | Euler | 2.5e-5 |
| 3 | RK2 | 5e-5 |
| 4 | RK2 | 2.5e-5 |
| 5 | RK4 | 5e-5 |
| 6 | RK4 | 2.5e-5 |

All run to t = 0.01. Analytical solution: `sin(pi*x)*sin(pi*y)*exp(-2*pi^2*t)`.

**Save**: field at t=0.01 for each case, plus L2 error against analytical.

**Expected error ratios** (coarse dt / fine dt):
- Euler: ~2
- RK2: ~4
- RK4: ~16

---

### REF-4.7: RK4 at larger timestep

| Parameter | Value |
|-----------|-------|
| Domain | [0, 1] x [0, 1] |
| Grid | 101 x 101 |
| D | 1.0 |
| Equation | `du/dt = D * laplacian(u)` |
| IC | `u(x,y) = sin(pi*x) * sin(pi*y)` |
| BC | Dirichlet u=0 all edges |

The Euler stability limit for this grid is approximately `dt_max = dx^2 / (4*D) ~ 2.5e-5`.

Run two cases:
- **Euler** with dt = 2.5e-5 (just stable), to t = 0.01
- **RK4** with dt = 3e-5 (~1.2x the Euler limit), to t = 0.01

**Save**: field at t=0.01 for both. Both should agree with the analytical solution.

**Notes**: RK4's stability region for diffusion (pure negative real eigenvalues) extends to about 2.78x the Forward Euler limit, so dt=3e-5 (~1.2x Euler limit) is safely within RK4's stable range. The original spec claimed 4x, but RK4's advantage is primarily in accuracy order, not a large stability region expansion for diffusion. For reference, the RK4 stability limit on this grid is approximately 3.5e-5.

**Also run** Euler with dt = 1e-4 — this should diverge (the test code will verify the stability monitor catches it; no reference needed for the diverged case).

---

### Property-only tests (Stage 4, no reference needed)

**PROP-4.1: Conservative advection**
- Domain: [0, 2*pi] x [0, 2*pi], Grid: 101x101
- Velocity: `v = (-y + pi, x - pi)` (solid-body rotation around center)
- IC: `u(x,y) = exp(-((x-pi-1)^2 + (y-pi)^2)/0.3)`
- BC: Periodic
- dt=0.01, Forward Euler, run to t = 2*pi (one full rotation)
- Check: `integral(u) dx dy` at t=0, pi/2, pi, 3*pi/2, 2*pi should be constant within 1%

**PROP-4.2: Wave equation energy**
- Domain: [0, 2*pi] x [0, 2*pi], Grid: 101x101
- Two fields: `u` (displacement) and `v` (velocity = du/dt)
- Equations: `du/dt = v`, `dv/dt = c^2 * laplacian(u)` with c=1.0
- IC: `u(x,y) = sin(x)*sin(y)`, `v(x,y) = 0`
- BC: Periodic
- Laplacian: use **finite-difference** (not spectral) — spectral Laplacian resolves all wavenumbers exactly, making the highest-frequency modes dominate and causing Euler to blow up quickly; FD Laplacian has a smaller max eigenvalue so Euler drifts but doesn't explode
- dt=0.005, run to t=10.0 with each method (Euler, RK2, RK4)
- Track `E = integral(v^2 + c^2*|grad(u)|^2) dx dy` at t=0, 1, 2, ..., 10
- Check: RK4 energy drift (max |E(t)-E(0)|/E(0)) is at least 10x smaller than Euler's

---

### REF-4.8: Complex Schrodinger

| Parameter | Value |
|-----------|-------|
| Domain | [0, 20] x [0, 20] |
| Grid | 201 x 201 |
| D | 1.0 |
| IC | `psi(x,y) = exp(-((x-10)^2 + (y-10)^2) / (2*1.5^2)) * exp(2j*x)` (Gaussian wave packet with momentum) |
| Equation | `d(psi)/dt = 1j * D * laplacian(psi)` |
| BC | Periodic in both x and y |
| dt | 0.005 |
| Stepping | Exact spectral integration |

**Snapshots**: `|psi|^2` and `angle(psi)` at t = 0.5, 1.0, 2.0. Also save `integral(|psi|^2) dx dy` at each snapshot (including at t=0).

**Notes**: Forward Euler is **unconditionally unstable** for the Schrodinger equation because its eigenvalues are purely imaginary (the Euler amplification factor |1 + i*lambda*dt| > 1 for all nonzero imaginary lambda). The reference uses exact spectral integration: in Fourier space, `psi_hat(t+dt) = psi_hat(t) * exp(-1j * D * k² * dt)`. This is unitary and preserves probability exactly. The wave packet should translate (due to the initial momentum `exp(2j*x)`) and spread. Domain is large enough with periodic BCs that the packet doesn't wrap around significantly by t=2.

---

### Property-only tests (Stage 4, additional)

**PROP-4.3: Schrodinger probability conservation**
- Same setup as REF-4.8
- Check `integral(|psi|^2)` at t=0.5, 1.0, 2.0 matches t=0 value within 1% relative

