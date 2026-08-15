# db/repositories/ — the only place SQL may appear

One module per table. Every function takes `conn` as its first parameter.

## Hard rules

- **SQL strings exist here and nowhere else in the project.** When a column is
  renamed, this folder is the only place to grep.
- Raise `ValueError` when a lookup finds nothing. Never let a `psycopg2`
  exception escape — the moment it does, `usecases/` has to know about psycopg2.
- Return plain dicts / lists (see `_rows.py`). No domain objects, no view models.
- Do not import from `usecases/`, `calc/`, `interfaces/`, or `agent/`.

## Add ORDER BY when the caller shows the result to a user

Without it, row order is physical storage order. That differs between a DB
built by `scripts.etl.build` and one loaded from `data/sql/`, because
`dump_sql.py` writes rows sorted by primary key. Same repo, different screen.

`rules_repo` hit exactly this: the weather / terrain / status dropdowns came
out alphabetical instead of in game order. Those three tables now carry a
`sort_order` column and the queries order by it.

## Adding a table

Also add it to `schema.ALL_TABLES` in `scripts/etl/schema.py` — that list
builds the teardown SQL, and a table missing from it survives a rebuild and
then collides on the next one.
