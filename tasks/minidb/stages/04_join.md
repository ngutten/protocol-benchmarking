# Stage 4: JOIN

## Goal

Add inner join support to the query engine.

## Requirements

### 1. INNER JOIN

```sql
SELECT ... FROM table1 JOIN table2 ON condition
```

- Only inner join is required.
- The ON condition can use any expression valid in WHERE.

### 2. Column disambiguation

- When both tables have a column with the same name, it must be qualified: `table1.col` or `table2.col`.
- Unqualified column names that exist in only one table resolve unambiguously.
- `SELECT *` from a join returns all columns from both tables; duplicate names are prefixed with the table name: `table1.col`, `table2.col`.

### 3. Self-join

```sql
SELECT ... FROM t AS t1 JOIN t AS t2 ON ...
```

Table aliases must be supported for self-joins.

### 4. Cross-type join conditions

The ON condition follows the same type coercion rules as WHERE:
- String to numeric: if the string parses as a number, coerce. Otherwise, comparison yields `false`.
- Boolean to numeric: `true` → 1, `false` → 0.
- All other cross-type comparisons yield `false`.
- Null yields `null` (three-valued logic).

## Interaction with existing features

- WHERE, ORDER BY, LIMIT, GROUP BY all work with joined results.
- Aggregate functions work over joined result sets.

## Out of scope

- LEFT/RIGHT/OUTER joins
- Multiple joins in one query (only two tables)
- CONTAINS, FLATTEN, user-defined coercion
