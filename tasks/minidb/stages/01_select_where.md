# Stage 1: Basic SELECT/WHERE with Dynamic Typing

## Goal

Implement the core MiniDB engine: table creation, data insertion, and basic queries
with SELECT, WHERE, and the full dynamic type system.

## Requirements

### Must implement:

1. **Engine process**: a program that reads commands from stdin (one per line) and
   writes JSON responses to stdout (one per line). See spec.md for response format.

2. **DDL**: `CREATE TABLE name (col1, col2, ...)` and `DROP TABLE name`.

3. **DML**: `INSERT INTO name VALUES (...)` including multi-row insert.
   All literal types must be supported:
   - Integers and floats
   - Strings (single-quoted, `''` for escape)
   - Booleans (`true`, `false`)
   - `null`
   - Blob hex literals: `x'...' AS 'mime/type'`
   - Lists: `[1, 'a', true, null]` (nested allowed)
   - Timestamps: `ts'2025-03-15T10:30:00Z'`

4. **SELECT**: `SELECT expr1 [AS alias], expr2, ... FROM table [WHERE condition]`

5. **Expressions**: arithmetic (`+`,`-`,`*`,`/`,`%`), comparison (`=`,`!=`,`<`,`>`,`<=`,`>=`),
   logical (`AND`, `OR`, `NOT`), `IS NULL`, `IS NOT NULL`, `TYPEOF(expr)`, `SIZEOF(expr)`,
   `CAST(expr AS typename)`.

6. **Type coercion**: follow the default coercion rules in spec.md exactly.
   - Cross-type comparisons
   - String-to-numeric coercion in comparisons
   - Boolean-to-numeric coercion
   - Null three-valued logic
   - Per-row arithmetic errors -> null + warning

7. **Error handling**: as specified in spec.md.

8. **SELECT ***: select all columns.

## Out of scope for this stage

- ORDER BY, LIMIT
- GROUP BY, aggregate functions
- JOIN
- CONTAINS, FLATTEN
- Session variables (SET)
- User-defined coercion rules

## Acceptance criteria

The engine should be startable as a subprocess and communicate correctly via
stdin/stdout JSON protocol. All type coercion rules must be followed precisely.
