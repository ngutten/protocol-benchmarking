# Stage 3: Aggregation and GROUP BY

## Goal

Add aggregate functions and grouping to the query engine.

## Requirements

### 1. SET command

```sql
SET variable = value
```

Session variables persist for the lifetime of the engine process.

Implement the `AGGREGATE_MODE` session variable: `'strict'` or `'lenient'` (default: `'lenient'`).

### 2. Aggregate functions

`COUNT(expr)`, `COUNT(*)`, `SUM(expr)`, `AVG(expr)`, `MIN(expr)`, `MAX(expr)`

- Without GROUP BY, aggregates operate over all rows matching WHERE.
- `SELECT COUNT(*) FROM t` must work.

### 3. GROUP BY

```sql
SELECT expr, agg(expr) FROM table [WHERE ...] GROUP BY expr1, expr2, ...
```

- Non-aggregated columns in SELECT must appear in GROUP BY (otherwise error).
- Groups with zero matching rows produce no output rows.

### 4. Lenient mode (default)

- `SUM`/`AVG`: skip non-numeric values. If no numeric values remain, return `null`.
- `MIN`/`MAX`: use cross-type ordering (the total ordering: `NULL < Boolean(false) < Boolean(true) < Numbers < Strings < Timestamps < Lists < Blobs`; within each type, natural ordering applies).
- `COUNT(expr)`: count non-null values of any type. `COUNT(*)`: count all rows.

### 5. Strict mode

- `SUM`/`AVG`: return `{"error": "..."}` for the whole query if any non-null value in the group is non-numeric.
- `MIN`/`MAX`: same as lenient (cross-type ordering is always well-defined).
- `COUNT`: same as lenient.

## Evaluation order

WHERE → GROUP BY → ORDER BY → LIMIT

- You can ORDER BY aggregate results.
- Type coercion rules apply within aggregate expressions.

## Out of scope

- HAVING (not part of MiniDB)
- JOIN, CONTAINS, FLATTEN, user-defined coercion
