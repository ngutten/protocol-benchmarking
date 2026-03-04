# Stage 1: Basic SELECT/WHERE with Dynamic Typing

## Goal

Implement the core MiniDB engine: table creation, data insertion, and basic queries
with SELECT, WHERE, and the full dynamic type system.

## Requirements

### 1. Engine process

A program that reads commands from stdin (one per line) and writes JSON responses
to stdout (one per line). Keywords are case-insensitive.

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

### 2. Response format

All responses are JSON objects, one per line:

- **Success with no data:** `{"ok": true}`
- **Query results:** `{"columns": [...], "rows": [[...], ...]}`
- **Errors:** `{"error": "description"}`
- **Warnings (per-row errors):** `{"columns": [...], "rows": [...], "warnings": ["..."]}`

Row values are JSON-encoded according to their type:

| Type | Literal syntax | JSON representation |
|------|---------------|---------------------|
| Integer | `42`, `-7` | JSON number (no decimal) |
| Float | `3.14`, `-0.5` | JSON number (with decimal) |
| String | `'hello'`, `'it''s'` | JSON string |
| Boolean | `true`, `false` | JSON boolean |
| Null | `null` | JSON null |
| Blob | `x'89504e...' AS 'image/png'` | `{"__blob__": true, "mime": "image/png", "size": 1234, "hash": "abcdef01"}` |
| List | `[1, 'a', true, null]` | JSON array (recursive, may contain blobs) |
| Timestamp | `ts'2025-03-15T10:30:00Z'` | `{"__ts__": "2025-03-15T10:30:00Z"}` |

### 3. DDL

```sql
CREATE TABLE name (col1, col2, ...)     -- no type declarations
DROP TABLE name
```

### 4. DML

```sql
INSERT INTO name VALUES (val1, val2, ...)
INSERT INTO name VALUES (val1, val2, ...), (val3, val4, ...)  -- multi-row

-- Blob insertion uses hex literal with MIME type:
INSERT INTO name VALUES (1, x'89504e470d0a1a0a...' AS 'image/png')

-- List insertion:
INSERT INTO name VALUES (1, [1, 'mixed', true, null])
```

All literal types must be supported: integers, floats, strings (single-quoted, `''`
for escape), booleans (`true`/`false`), `null`, blob hex literals, lists (nested
allowed), and timestamps.

### 5. SELECT

```sql
SELECT expr1 [AS alias], expr2, ... FROM table [WHERE condition]
SELECT * FROM table [WHERE condition]
```

### 6. Expressions and operators

- **Arithmetic:** `+`, `-`, `*`, `/`, `%`
- **Comparison:** `=`, `!=`, `<`, `>`, `<=`, `>=`
- **Logical:** `AND`, `OR`, `NOT`
- **Null checks:** `IS NULL`, `IS NOT NULL`
- **Type introspection:** `TYPEOF(expr)` returns one of: `'integer'`, `'float'`, `'string'`, `'boolean'`, `'null'`, `'blob'`, `'list'`, `'timestamp'`
- **Size:** `SIZEOF(expr)` returns byte size for blobs, character count for strings, element count for lists, `null` for other types.
- **Casting:** `CAST(expr AS typename)` — explicit coercion. Valid targets: `'integer'`, `'float'`, `'string'`, `'boolean'`. Errors on impossible conversions (per-row).

### 7. Type system

MiniDB is dynamically typed — there are NO column-level type declarations. A column
can hold any mix of types in different rows.

**Numeric interchangeability:** Integers and floats are collectively "numeric." Any
arithmetic or comparison between an integer and a float promotes the integer to float.
`1 = 1.0` is `true`. Integer division (`/`) between two integers returns an integer
(truncated toward zero). If either operand is float, the result is float.

### 8. Type coercion rules

**For comparisons (`=`, `!=`, `<`, `>`, `<=`, `>=`):**
- Numeric types: int ↔ float freely (as above).
- String to numeric: if the string parses as a number, coerce. Otherwise, the comparison yields `false` (not an error).
- Boolean to numeric: `true` → 1, `false` → 0.
- All other cross-type comparisons yield `false`.
- Any comparison involving `null` yields `null` (three-valued logic) EXCEPT `IS NULL` / `IS NOT NULL`.

**For arithmetic (`+`, `-`, `*`, `/`, `%`):**
- Numeric types: int ↔ float as above.
- String + String: concatenation (only for `+`).
- String + Numeric: coerce numeric to string, concatenate (only for `+`).
- All other cross-type arithmetic is an error (per-row; the row is excluded from results with a warning, not a query-level failure).

### 9. Error handling

- Parse errors: `{"error": "Parse error: ..."}`
- Reference to nonexistent table: `{"error": "No such table: name"}`
- Reference to nonexistent column: `{"error": "No such column: name"}`
- Column count mismatch in INSERT: `{"error": "Expected N values, got M"}`
- Per-row arithmetic errors in SELECT do NOT abort the query; the offending cell becomes `null` and a warning is included: `{"columns": [...], "rows": [...], "warnings": ["..."]}`

## Out of scope for this stage

- ORDER BY, LIMIT
- GROUP BY, aggregate functions
- JOIN
- CONTAINS, FLATTEN
- Session variables (SET)
- User-defined coercion rules
