# scripts/ — run by hand, not at runtime

Never installed. `pyproject.toml` has `where = ["src"]`, so `scripts/` stays
out of the distributed package.

## Hard rules

- `scripts/` may import `src/`. **`src/` must never import `scripts/`.**
  ETL runs every few months; `src/` runs on every request. Mixing them ships
  PokeAPI parsing code to users and breaks the app when PokeAPI changes shape.
- Run from the project root with `-m`: `python -m scripts.etl.build`.
  Never `sys.path.append` — that makes the working directory part of the code.
- These files may `print()` freely. That is the point of them.

## etl/ — three directions, do not confuse them

| | When | What |
|---|---|---|
| `load_sql.py` | every install | `data/sql/` -> DB. No API calls, seconds |
| `build.py` | new regulation | PokeAPI -> `data/sql/` -> DB. ~1,900 calls, minutes |
| `dump_sql.py` | after editing the DB | DB -> `data/sql/`, then commit |

`build.py` needs an empty DB and always re-fetches — it never reuses existing
files. Do not run it to "fix" a database.

`data/sql/` is committed and is the real distribution artifact. After any
change that alters DB contents, run `dump_sql.py` and commit the result, or
installs will not match your database.

`sync_usage.py` is the exception: usage snapshots accumulate daily and are
**not** part of `data/sql/`. `daily_usage.sh` runs it under launchd.
Always use `--backfill`, never "today only" — the source keeps 16 days and
a missed day is gone for good. Already-fetched dates are skipped, so
running it daily costs nothing.

## schema.py is the single source of DDL

Never write `CREATE TABLE` anywhere else, and never reverse-engineer DDL from
the live DB — that would drop every comment. Adding a table means adding it to
`ALL_TABLES` too.

## Generators

Each `get_*.py` exposes `FILENAME`, `TABLE`, `COLUMNS`, `DDL`, `build(conn)`.
A file holding a second table declares `EXTRA = [(DDL, table, columns)]` so
`dump_sql` finds it. Literal tables build through `parse_utils.literal_build`.
