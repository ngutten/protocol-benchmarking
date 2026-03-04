# Stage 6: User-Defined Coercion Rules

## Goal

Allow users to override the default type coercion behavior via session variables.
This is the implicit invalidation stage: changing coercion rules retroactively changes
the behavior of all previous features (WHERE, ORDER BY, aggregation, JOIN, CONTAINS).

## Requirements

1. **COERCE_RULES session variable**:
   ```sql
   SET COERCE_RULES = 'default'          -- restore default behavior
   SET COERCE_RULES = 'strict'           -- no implicit coercion; cross-type comparisons error
   SET COERCE_RULES = 'numeric'          -- coerce everything to numeric where possible, error otherwise
   SET COERCE_RULES = 'string'           -- coerce everything to string for comparisons
   ```

2. **'strict' mode**:
   - Any comparison between different types (except int/float) returns an error (per-row, same as arithmetic errors: null + warning).
   - Arithmetic between different types (except int/float) returns an error.
   - This means `WHERE score > 5` fails on rows where `score` is a string, even if the string is '10'.

3. **'numeric' mode**:
   - All comparisons attempt numeric coercion first.
   - Strings: parse as number or error. Booleans: true->1, false->0. Timestamps: epoch seconds.
   - Blobs and lists: error (per-row).

4. **'string' mode**:
   - All comparisons coerce both sides to string.
   - Numbers: decimal representation. Booleans: 'true'/'false'. Null: still null (three-valued).
   - Timestamps: ISO format string. Blobs: '<blob:mime:size>'. Lists: JSON representation.
   - This means `1 < 2` might become `'1' < '2'` which is true, but `9 < 10` becomes `'9' < '10'` which is... also true lexicographically. But `9 < 100` becomes `'9' < '100'` which is FALSE (lexicographic).
   - ORDER BY also uses string comparison in this mode.

5. **Interaction with existing features**:
   - WHERE: coercion rules change how conditions evaluate.
   - ORDER BY: in 'string' mode, ordering is purely lexicographic on string representations.
   - Aggregation: SUM/AVG in 'strict' mode error on any non-numeric even if they would normally coerce.
   - JOIN ON: coercion rules apply to the join condition.
   - CONTAINS: coercion rules apply to element comparison within lists.
   - CAST is NOT affected by coercion rules (CAST is always explicit).

6. **COERCE_RULES can be changed multiple times** within a session and takes effect immediately.

## Why this is tricky

If the implementation hardcodes coercion behavior in comparison/arithmetic functions,
adding configurable coercion requires threading a coercion strategy through the entire
evaluation pipeline. If the implementation already uses a clean separation between
evaluation and coercion, this is straightforward. This stage specifically tests whether
the earlier implementation anticipated this kind of extensibility.

## Out of scope

- Custom user-defined coercion functions (only the four predefined modes)
- Per-column or per-table coercion rules
