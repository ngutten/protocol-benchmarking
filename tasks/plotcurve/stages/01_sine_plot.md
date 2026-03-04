# Stage 1: Sine Wave Plot

## Goal

Create a Python script `plotcurve.py` that plots the function `sin(2*pi*x/5)` and saves it as a PNG file.

## Requirements

### Interface

The script reads a single JSON line from stdin and writes a single JSON line to stdout.

**Input JSON fields:**
| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `x_min` | float | -10 | Left bound of x-axis |
| `x_max` | float | 10 | Right bound of x-axis |
| `n_points` | int | 500 | Number of sample points |
| `output` | string | `"plot.png"` | Output file path |
| `title` | string | `""` | Optional plot title |

All fields are optional; defaults are used for missing fields.

**Output JSON (success):**
```json
{"ok": true, "output": "plot.png"}
```

**Output JSON (error):**
```json
{"error": "description"}
```

### Plot specifications

- Plot the function `f(x) = sin(2 * pi * x / 5)` over the given x range.
- The x-axis must be labeled `x` and the y-axis `f(x)`.
- The plot must include a grid.
- The curve must be a solid blue line.
- If `title` is provided and non-empty, display it as the plot title.
- Save to the path specified by `output` as a PNG with at least 100 DPI.
- Use matplotlib for plotting.

### Error handling

- If `x_min >= x_max`, return `{"error": "x_min must be less than x_max"}`.
- If `n_points < 2`, return `{"error": "n_points must be at least 2"}`.
- If the input is not valid JSON, return `{"error": "invalid JSON input"}`.

### Implementation notes

- The script should be runnable with `python3 plotcurve.py`.
- It reads exactly one line from stdin, processes it, and exits.
- Use only the standard library plus `numpy` and `matplotlib`.
