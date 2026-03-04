# Stage 2: ORDER BY and LIMIT

## Goal

Add sorting and result limiting to the existing query engine.

## Requirements

1. **ORDER BY**: `SELECT ... FROM ... [WHERE ...] ORDER BY expr1 [ASC|DESC], expr2 [ASC|DESC], ...`
   - Default direction is ASC.
   - Multiple sort keys: sort by first key, break ties with second key, etc.
   - **Cross-type ordering** must follow the type hierarchy defined in spec.md:
     `NULL < Boolean(false) < Boolean(true) < Numbers < Strings < Timestamps < Lists < Blobs`
   - Within-type: natural ordering (numeric, lexicographic, chronological).
   - Lists: lexicographic by element using the same cross-type ordering.
   - Blobs: by size, then by hash (lexicographic).
   - DESC reverses the entire ordering (including cross-type).

2. **LIMIT**: `SELECT ... FROM ... [WHERE ...] [ORDER BY ...] LIMIT n`
   - Returns at most n rows.
   - Without ORDER BY, which n rows are returned is deterministic but implementation-defined.

## Interaction with existing features

- ORDER BY expressions can use any expression valid in SELECT (arithmetic, TYPEOF, etc).
- WHERE is evaluated before ORDER BY; LIMIT is applied after ORDER BY.

## Out of scope

- OFFSET, GROUP BY, aggregation, JOIN, CONTAINS, FLATTEN, SET
