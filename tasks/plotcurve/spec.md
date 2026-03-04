# PlotCurve: LaTeX Math Function Plotter

## Overview

PlotCurve is a Python command-line tool that plots mathematical functions.
It reads a function definition and parameters from a JSON request on stdin,
renders the plot to a PNG file, and returns a JSON response on stdout.

## Protocol

Communication is via single-line JSON over stdin/stdout.

**Request format:**
```json
{"function": "<definition>", "x_min": -10, "x_max": 10, "n_points": 500, "output": "plot.png"}
```

**Response format (success):**
```json
{"ok": true, "output": "plot.png"}
```

**Response format (error):**
```json
{"error": "description of what went wrong"}
```

## Stages

1. **Sine Plot** — Plot `sin(2*pi*x/5)` with configurable range and output path.
2. **LaTeX Functions** — Parse arbitrary LaTeX math expressions like `\sin(x)`, `\frac{x^2}{1+x}`, `e^{-x^2}` and plot them.
