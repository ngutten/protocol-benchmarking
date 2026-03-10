# Stage 4: Diagnostics

## Goal

Add flow diagnostic computations: drag and lift forces on obstacles, mass flux
through boundaries, kinetic energy, and enstrophy. Support config-driven
diagnostic selection and time history tracking.

## Requirements

### 1. `get_diagnostics` command

Return computed diagnostic values for the current solution state.

```json
{"command": "get_diagnostics"}
```

Response:
```json
{
  "drag": 2.05,
  "lift": 0.001,
  "mass_flux": {"left": 0.5, "right": 0.5, "top": 0.0, "bottom": 0.0},
  "kinetic_energy": 0.0234,
  "enstrophy": 1.456
}
```

Only diagnostics that have been enabled (via config or by having obstacles present)
are included in the response.

### 2. Diagnostic definitions

#### Drag and lift
Forces exerted by the fluid on obstacles. Computed by integrating pressure and
viscous stress over obstacle surfaces.

- **Drag**: force component in the primary flow direction (x by default)
- **Lift**: force component perpendicular to the primary flow direction (y by default)

These are only available when obstacles are present. If no obstacles exist, these
fields are omitted from the response.

#### Mass flux
Volume flow rate through each domain boundary:
```
Q = ∫ u·n dS
```
where `n` is the outward normal. Positive means flow out of the domain.

#### Kinetic energy
Domain-integrated kinetic energy per unit depth:
```
KE = (1/2) ∫∫ (u² + v²) dA
```

#### Enstrophy
Domain-integrated enstrophy:
```
Z = (1/2) ∫∫ ω² dA
```

### 3. `get_diagnostic_history` command

Return the time series of a diagnostic value, recorded at each `step` call.

```json
{"command": "get_diagnostic_history", "diagnostic": "drag"}
```

Response:
```json
{"times": [0.0, 0.01, 0.02, ...], "values": [2.1, 2.05, 2.03, ...]}
```

If no time-dependent simulation has been run, returns empty arrays.

### 4. Config-driven diagnostics

The `load_config` command (from Stage 3) can include a `diagnostics` section:

```json
{
  "grid": {...},
  "fluid": {...},
  "boundaries": {...},
  "obstacles": [...],
  "diagnostics": ["drag", "lift", "mass_flux", "kinetic_energy", "enstrophy"]
}
```

When specified, only the listed diagnostics are computed and recorded. When not
specified, all applicable diagnostics are computed.

### 5. Error handling

- Requesting history of unknown diagnostic: `{"error": "Unknown diagnostic: name"}`
- `get_diagnostics` before solving: `{"error": "No solution available"}`

## Internal state access test

Computing drag and lift requires access to pressure and viscous stress fields at
obstacle surfaces. Computing enstrophy requires the vorticity field. If these
quantities are not cleanly exposed internally, this stage forces refactoring of
the solver's data access patterns.

## Out of scope

- Force decomposition (pressure drag vs viscous drag)
- Strouhal number computation
- Spectral analysis
- Multigrid
