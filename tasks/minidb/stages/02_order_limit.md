# Stage 2: ORDER BY and LIMIT

## Goal

Add sorting and result limiting to the existing query engine.

## Requirements

### 1. ORDER BY

```sql
SELECT ... FROM ... [WHERE ...] ORDER BY expr1 [ASC|DESC], expr2 [ASC|DESC], ...
```

- Default direction is ASC.
- Multiple sort keys: sort by first key, break ties with second key, etc.
- ORDER BY expressions can use any expression valid in SELECT (arithmetic, TYPEOF, etc).

### 2. Cross-type ordering

For ORDER BY on columns with mixed types, the total ordering is:

```
NULL < Boolean(false) < Boolean(true) < Numbers < Strings < Timestamps < Lists < Blobs
```

Within each type, natural ordering applies:
- **Numbers:** numeric ordering (integers and floats interleave naturally)
- **Strings:** lexicographic ordering
- **Timestamps:** chronological ordering
- **Lists:** lexicographic by element using the same cross-type ordering
- **Blobs:** by size, then by hash (lexicographic)

DESC reverses the entire ordering (including cross-type).

### 3. LIMIT

```sql
SELECT ... FROM ... [WHERE ...] [ORDER BY ...] LIMIT n
```

- Returns at most `n` rows.
- Without ORDER BY, which `n` rows are returned is deterministic but implementation-defined.

## Evaluation order

WHERE → ORDER BY → LIMIT

## Out of scope

- OFFSET, GROUP BY, aggregation, JOIN, CONTAINS, FLATTEN, SET
