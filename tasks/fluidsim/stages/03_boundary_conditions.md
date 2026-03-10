# Stage 3: Complex Boundary Conditions

## Goal

Add support for inflow, outflow, and periodic boundary conditions, as well as
immersed boundary obstacles (circles and rectangles).

## Requirements

### 1. New boundary condition types

Extend `set_boundary` to accept the following additional types:

#### `inflow`
Prescribed velocity at an inlet. Requires `profile` parameter:
- `"uniform"`: constant velocity, requires `velocity: [vx, vy]`
- `"parabolic"`: parabolic velocity profile (Poiseuille-like), requires `velocity_max: float` — peak velocity at the center of the edge; velocity is zero at the corners of that edge.

```json
{"command": "set_boundary", "boundary": "left", "type": "inflow", "profile": "parabolic", "velocity_max": 1.5}
```

Response: `{"status": "ok"}`

#### `outflow`
Zero-gradient (Neumann) boundary condition at an outlet. No additional parameters needed.

```json
{"command": "set_boundary", "boundary": "right", "type": "outflow"}
```

Response: `{"status": "ok"}`

#### `periodic`
Periodic boundary condition. Must be paired: if left is periodic, right must also be
periodic (and vice versa for top/bottom).

```json
{"command": "set_boundary", "boundary": "left", "type": "periodic", "paired_with": "right"}
{"command": "set_boundary", "boundary": "right", "type": "periodic", "paired_with": "left"}
```

Response: `{"status": "ok"}`

Error if paired edges don't match: `{"error": "Periodic boundaries must be paired"}`

### 2. `add_obstacle` command

Add immersed boundary obstacles to the domain.

#### Circle
```json
{"command": "add_obstacle", "type": "circle", "center": [0.5, 0.5], "radius": 0.1}
```

#### Rectangle
```json
{"command": "add_obstacle", "type": "rectangle", "lower_left": [0.3, 0.3], "upper_right": [0.5, 0.5]}
```

Response: `{"obstacle_id": int}` — a unique integer identifier for the obstacle.

Obstacles enforce no-slip conditions on their surfaces. The implementation method
(direct forcing, interpolated IBM, cut-cell, etc.) is left to the implementer.

### 3. `load_config` command

Load a complete simulation configuration from a JSON file.

```json
{"command": "load_config", "path": "config.json"}
```

The config file format:
```json
{
  "grid": {"nx": 64, "ny": 64, "lx": 2.0, "ly": 1.0},
  "fluid": {"viscosity": 0.01},
  "force": [0.0, 0.0],
  "boundaries": {
    "top": {"type": "no_slip"},
    "bottom": {"type": "no_slip"},
    "left": {"type": "inflow", "profile": "parabolic", "velocity_max": 1.5},
    "right": {"type": "outflow"}
  },
  "obstacles": [
    {"type": "circle", "center": [0.5, 0.5], "radius": 0.1}
  ]
}
```

Response: `{"status": "ok"}`

This should be equivalent to calling `create`, `set_boundary`, and `add_obstacle`
individually.

### 4. Error handling

- Invalid boundary type: `{"error": "Invalid boundary type: name"}`
- Unpaired periodic boundary: `{"error": "Periodic boundaries must be paired"}`
- Invalid obstacle type: `{"error": "Invalid obstacle type: name"}`
- Obstacle outside domain: `{"error": "Obstacle outside domain"}`
- Config file not found: `{"error": "Config file not found: path"}`

## Modularity test

Boundary conditions interact deeply with the solver discretization. If the Stage 1/2
implementation hardcodes boundary handling inside the solver loop, adding new BC types
requires modifying core solver code. Well-separated boundary condition handling makes
this stage much easier.

## Out of scope

- Moving obstacles
- Adaptive mesh refinement near obstacles
- Diagnostics (drag, lift)
- Multigrid
