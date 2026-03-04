# Stage 4: JOIN

## Goal

Add inner join support to the query engine.

## Requirements

1. **INNER JOIN**: `SELECT ... FROM table1 JOIN table2 ON condition`
   - Only inner join is required.
   - The ON condition can use any expression valid in WHERE.

2. **Column disambiguation**:
   - When both tables have a column with the same name, it must be qualified: `table1.col` or `table2.col`.
   - Unqualified column names that exist in only one table resolve unambiguously.
   - `SELECT *` from a join returns all columns from both tables; duplicate names are prefixed with the table name: `table1.col`, `table2.col`.

3. **Self-join**: `SELECT ... FROM t AS t1 JOIN t AS t2 ON ...`
   - Table aliases must be supported for self-joins.

4. **Cross-type join conditions**: The ON condition follows the same coercion rules as WHERE. Joining a string column against an integer column should coerce per the default rules.

## Interaction with existing features

- WHERE, ORDER BY, LIMIT, GROUP BY all work with joined results.
- Aggregate functions work over joined result sets.
- Type coercion in the ON condition follows the same rules as in WHERE.

## Out of scope

- LEFT/RIGHT/OUTER joins
- Multiple joins in one query (only two tables)
- CONTAINS, FLATTEN, user-defined coercion
