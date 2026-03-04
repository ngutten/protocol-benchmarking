# MiniDB: A Dynamically-Typed Multimedia Query Engine

## Overview

Implement an in-memory query engine for dynamically-typed, heterogeneous tables.
Unlike a traditional SQL database, MiniDB tables have **no column schemas** —
any cell can hold any type, and types can vary freely within a column. The engine
must handle type coercion, mixed-type operations, and binary blob data gracefully.

## External Interface

The engine MUST be usable as a subprocess that communicates via **stdin/stdout**.
Commands are sent one per line. Results are returned as JSON, one response per command.

```
> CREATE TABLE t (a, b, c)
{"ok": true}

> INSERT INTO t VALUES (1, 'hello', 3.14)
{"ok": true}

> SELECT a, b FROM t WHERE b = 'hello'
{"columns": ["a", "b"], "rows": [[1, "hello"]]}

> ERROR
{"error": "Parse error: unexpected token 'ERROR'"}
```

This interface must be language-agnostic: the same test suite must work
whether the engine is implemented in Python, C++, or anything else.

### Response format

- Success with no data: `{"ok": true}`
- Query results: `{"columns": [...], "rows": [[...], ...]}`
- Errors: `{"error": "description"}`

Row values are JSON-encoded: numbers as JSON numbers, strings as JSON strings,
booleans as JSON booleans, null as JSON null, blobs as `{"__blob__": true, "mime": "image/png", "size": 1234, "hash": "abcdef01"}`,
lists as JSON arrays (recursive, may contain blobs).

## Data Types

### Type System

MiniDB supports the following types. There is NO column-level type declaration —
a column can hold any mix of these in different rows.

| Type | Literal syntax | JSON representation |
|------|---------------|---------------------|
| Integer | `42`, `-7` | JSON number (no decimal) |
| Float | `3.14`, `-0.5` | JSON number (with decimal) |
| String | `'hello'`, `'it''s'` | JSON string |
| Boolean | `true`, `false` | JSON boolean |
| Null | `null` | JSON null |
| Blob | (no literal; inserted via special syntax) | `{"__blob__": ...}` |
| List | `[1, 'a', true, null]` | JSON array |
| Timestamp | `ts'2025-03-15T10:30:00Z'` | `{"__ts__": "2025-03-15T10:30:00Z"}` |

### Numeric Interchangeability

Integers and floats are collectively "numeric." Any arithmetic or comparison between
an integer and a float promotes the integer to float. `1 = 1.0` is `true`.
Integer division (`/`) between two integers returns an integer (truncated toward zero).
If either operand is float, the result is float.

### Type Coercion Rules (Default)

When a comparison or arithmetic operator encounters operands of different types,
the following coercion rules apply by default:

**For comparisons (`=`, `!=`, `<`, `>`, `<=`, `>=`):**
- Numeric types: int <-> float freely (as above)
- String to numeric: if the string parses as a number, coerce. Otherwise, the comparison yields `false` (not an error).
- Boolean to numeric: `true` -> 1, `false` -> 0.
- All other cross-type comparisons yield `false`.
- Any comparison involving `null` yields `null` (three-valued logic) EXCEPT `IS NULL` / `IS NOT NULL`.

**For arithmetic (`+`, `-`, `*`, `/`, `%`):**
- Numeric types: int <-> float as above.
- String + String: concatenation (only for `+`).
- String + Numeric: coerce numeric to string, concatenate (only for `+`).
- All other cross-type arithmetic is an error (per-row; the row is excluded from results with a warning, not a query-level failure).

### Cross-Type Ordering

For `ORDER BY` on columns with mixed types, the total ordering is:

```
NULL < Boolean(false) < Boolean(true) < Numbers < Strings < Timestamps < Lists < Blobs
```

Within each type, natural ordering applies (numeric, lexicographic, chronological, etc).
Lists are ordered lexicographically by element using the same cross-type ordering.
Blobs are ordered by size, then by hash (lexicographic).

## SQL Dialect

The query language is a subset of SQL with some extensions. Keywords are case-insensitive.

### DDL

```sql
CREATE TABLE name (col1, col2, ...)     -- no types
DROP TABLE name
```

### DML

```sql
INSERT INTO name VALUES (val1, val2, ...)
INSERT INTO name VALUES (val1, val2, ...), (val3, val4, ...)  -- multi-row

-- Blob insertion uses a special hex literal:
INSERT INTO name VALUES (1, x'89504e470d0a1a0a...' AS 'image/png')
-- The x'...' is hex-encoded bytes, AS 'mime' specifies the MIME type.

-- List insertion:
INSERT INTO name VALUES (1, [1, 'mixed', true, null])
```

### Queries

```sql
SELECT expr1 [AS alias1], expr2, ... FROM table [WHERE condition]
  [GROUP BY expr1, expr2, ...]
  [ORDER BY expr1 [ASC|DESC], ...]
  [LIMIT n]

SELECT ... FROM table1 JOIN table2 ON condition

-- Subqueries are NOT required.
```

### Expressions and Operators

**Arithmetic:** `+`, `-`, `*`, `/`, `%`
**Comparison:** `=`, `!=`, `<`, `>`, `<=`, `>=`
**Logical:** `AND`, `OR`, `NOT`
**Null checks:** `IS NULL`, `IS NOT NULL`
**Type introspection:** `TYPEOF(expr)` returns one of: `'integer'`, `'float'`, `'string'`, `'boolean'`, `'null'`, `'blob'`, `'list'`, `'timestamp'`
**Size:** `SIZEOF(expr)` returns byte size for blobs, character count for strings, element count for lists, `null` for other types.
**List operations:** `expr CONTAINS value` (true if list contains value), `FLATTEN(column)` is a table-valued operation (see below).
**Casting:** `CAST(expr AS typename)` -- explicit coercion. Valid targets: `'integer'`, `'float'`, `'string'`, `'boolean'`. Errors on impossible conversions (per-row).

### FLATTEN

`FLATTEN(column)` is used in the FROM clause and expands list-valued cells into rows:

```sql
-- If table t has: id=1, tags=['a','b','c'] and id=2, tags='single'
SELECT id, FLATTEN(tags) AS tag FROM t
-- Produces: (1,'a'), (1,'b'), (1,'c'), (2,'single')
-- Non-list values are passed through as a single row.
-- NULL values produce a single row with NULL.
```

### Aggregate Functions

`COUNT(expr)`, `COUNT(*)`, `SUM(expr)`, `AVG(expr)`, `MIN(expr)`, `MAX(expr)`

Aggregation has two modes, controlled by a session variable:

```sql
SET AGGREGATE_MODE = 'strict'   -- error if any row has incompatible type
SET AGGREGATE_MODE = 'lenient'  -- skip rows with incompatible types (default)
```

In lenient mode:
- `SUM`/`AVG`: skip non-numeric values. If no numeric values remain, return `null`.
- `MIN`/`MAX`: use cross-type ordering (so MIN over mixed types returns the "smallest" by type hierarchy).
- `COUNT(expr)`: count non-null values (any type). `COUNT(*)` counts all rows.

In strict mode:
- `SUM`/`AVG`: return `{"error": "..."}` for the whole query if any non-null value in the group is non-numeric.
- `MIN`/`MAX`: same as lenient (cross-type ordering is always well-defined).
- `COUNT`: same as lenient.

## Session Variables

```sql
SET variable = value
```

Session variables persist for the lifetime of the engine process. Defined variables:

- `AGGREGATE_MODE`: `'strict'` or `'lenient'` (default: `'lenient'`)

*Stage 6 will add `COERCE_RULES` as an additional session variable.*

## Error Handling

- Parse errors return `{"error": "Parse error: ..."}`.
- Reference to nonexistent table: `{"error": "No such table: name"}`.
- Reference to nonexistent column: `{"error": "No such column: name"}`.
- Column count mismatch in INSERT: `{"error": "Expected N values, got M"}`.
- Per-row arithmetic errors in SELECT do NOT abort the query; the offending cell becomes `null` and a warning is included: `{"columns": [...], "rows": [...], "warnings": ["..."]}`.
- Aggregate errors in strict mode abort the query.
