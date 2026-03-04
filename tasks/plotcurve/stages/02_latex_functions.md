# Stage 2: LaTeX Function Parser

## Goal

Extend `plotcurve.py` to accept arbitrary mathematical functions written in LaTeX notation and plot them. Only elementary functions need to be supported.

## Requirements

### New input field

Add a `function` field to the input JSON. When present, this LaTeX string defines the function to plot instead of the hardcoded sine wave.

```json
{"function": "\\sin(x)", "x_min": -6.28, "x_max": 6.28, "output": "sine.png"}
```

If `function` is absent or empty, fall back to the original `sin(2*pi*x/5)`.

### Supported LaTeX constructs

The parser must handle these elementary functions and operators:

**Arithmetic:**
- `+`, `-`, `*` (or implicit multiplication), `/`
- `\cdot` for multiplication: `2 \cdot x` → `2 * x`
- `\frac{a}{b}` → `a / b`
- Parentheses `(...)` for grouping

**Powers and roots:**
- `x^2` → `x**2`
- `x^{2n+1}` → `x**(2*n+1)` (braced exponents)
- `\sqrt{x}` → `sqrt(x)`
- `\sqrt[3]{x}` → `x**(1/3)` (nth root)

**Trigonometric:**
- `\sin(x)`, `\cos(x)`, `\tan(x)`
- `\arcsin(x)`, `\arccos(x)`, `\arctan(x)`

**Exponential and logarithmic:**
- `e^{x}` or `\exp(x)` → `exp(x)`
- `\ln(x)` → `log(x)` (natural log)
- `\log(x)` → `log10(x)` (base-10 log)
- `\log_{2}(x)` → `log2(x)` (base-N log for integer bases)

**Constants:**
- `\pi` → `pi`
- `e` (Euler's number) when used as base of exponent

**Implicit multiplication:**
- `2x` → `2*x`
- `3\sin(x)` → `3*sin(x)`
- `x \cos(x)` → `x*cos(x)`

### Evaluation

- The function is evaluated at each sample point using numpy.
- Points where the function is undefined (division by zero, log of negative, etc.) should produce `NaN` and be skipped in the plot (matplotlib handles NaN gaps automatically).
- The y-axis should auto-scale but be clipped to `[-100, 100]` to avoid extreme values from asymptotes.

### Plot labeling

- The y-axis label should be the LaTeX string rendered as-is (e.g., `$\sin(x)$`), wrapped in `$...$` for matplotlib's LaTeX rendering.
- If no `title` is given, use the LaTeX function string as the title (also in `$...$`).

### Error handling

- If the LaTeX string contains unsupported constructs, return `{"error": "unsupported LaTeX: <detail>"}`.
- If the function string is malformed (unbalanced braces, etc.), return `{"error": "parse error: <detail>"}`.

### Examples

| Input `function` | Evaluates as |
|-----------------|--------------|
| `\sin(x)` | `sin(x)` |
| `x^2 - 3x + 1` | `x**2 - 3*x + 1` |
| `\frac{x^2}{1 + x^2}` | `x**2 / (1 + x**2)` |
| `e^{-x^2}` | `exp(-x**2)` |
| `\sqrt{x^2 + 1}` | `sqrt(x**2 + 1)` |
| `\ln(\sin(x))` | `log(sin(x))` |
| `\frac{1}{2}\cos(2\pi x)` | `(1/2)*cos(2*pi*x)` |
| `\arctan(\frac{1}{x})` | `arctan(1/x)` |

### Backward compatibility

- All Stage 1 behavior must be preserved (default sine wave, validation, etc.).
- The `function` field is purely additive.
