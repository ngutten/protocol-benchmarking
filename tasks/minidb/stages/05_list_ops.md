# Stage 5: List Operations

## Goal

Add list-specific query operations to the engine.

## Requirements

### 1. CONTAINS operator

`expr CONTAINS value`

- Returns `true` if `expr` evaluates to a list containing `value`.
- Comparison uses the same type coercion rules as WHERE: `[1, 2, 3] CONTAINS '2'` is `true` (string `'2'` coerces to numeric 2).
- If `expr` is not a list, returns `false` (not an error).
- If `expr` is null, returns `null`.
- Usable in WHERE, ON, and any boolean expression context.

### 2. FLATTEN

```sql
SELECT cols, FLATTEN(listcol) AS alias FROM table
```

- FLATTEN appears in the SELECT clause but has table-valued semantics.
- For each row, if `listcol` is a list, produce one output row per element.
- If `listcol` is not a list (including null), produce one output row with the value as-is.
- The flattened column takes the alias name.
- Other columns in the same row are duplicated across the expanded rows.
- Only one FLATTEN per query.

### 3. Nested lists

FLATTEN only expands one level. `FLATTEN([1, [2, 3]])` produces rows `1` and `[2, 3]`.

## Evaluation order

WHERE → FLATTEN → GROUP BY → ORDER BY → LIMIT

- WHERE is applied before FLATTEN.
- ORDER BY, LIMIT, GROUP BY operate on the post-FLATTEN result set.
- Aggregation over flattened results works normally.
- CONTAINS works in JOIN ON conditions.
- FLATTEN + GROUP BY: you can GROUP BY the flattened column.

## Out of scope

- Recursive/deep flatten
- List construction in SELECT (e.g., collecting into a list)
- User-defined coercion rules
