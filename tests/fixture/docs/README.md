# TinyCalc

TinyCalc is a minimal calculator library. It exposes three public functions:

- `add(a, b)` — returns the sum of `a` and `b` **as a formatted string** (e.g. `"5.00"`).
- `multiply(a, b)` — returns the product of `a` and `b`.
- `subtract(a, b)` — returns `a - b`.

## Configuration

The output precision is controlled by the `CALC_PRECISION` environment variable
(default: `2`). Setting `CALC_PRECISION=4` will make `add` return values with
four decimal places.

## CLI

Run the module directly:

```
python app.py --verbose
```

The `--verbose` flag prints the full call trace for debugging.
