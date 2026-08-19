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
| `build.py` | new regulation | PokeAPI -> DB. ~1,900 calls, minutes |
| `dump_sql.py` | after editing the DB | DB -> `data/sql/`, then commit |

`build.py` needs an empty DB and always re-fetches. **It does not write
`data/sql/`** — only `dump_sql.py` does. Do not run `build.py` to "fix" a
database.

`data/sql/` is two files and is the seed for rebuilding (new machine, disaster
recovery, CI):

| | From | What |
|---|---|---|
| `00_schema.sql` | `schema.py` | every `CREATE TYPE` / `CREATE TABLE`, parents first |
| `01_content.sql` | the live DB | every `INSERT`, in FK-safe order |

After any change that alters DB contents, run `dump_sql.py` and commit the
result, or a rebuild will not match your database.

`sync/usage.py` is the exception: usage snapshots accumulate daily and are
**not** part of `data/sql/`. `daily_usage.sh` runs it under launchd.
Always use `--backfill`, never "today only" — a missed day is gone once the
source drops it. Already-fetched dates are skipped, so running it daily
costs nothing.

`--since` defaults to `SEASON_START` in `sync/usage.py`. The source's folder
names keep the old season label (2026-08-18 data still sits under `M4/`), so
the season boundary is a **date**, not the label. Bump `SEASON_START` when a
new regulation begins.

## schema.py is the single source of DDL

Never write `CREATE TABLE` anywhere else, and never reverse-engineer DDL from
the live DB — that would drop every comment.

Two lists carry the order, and adding a table means adding it to both:

- `CREATE_ORDER` — `(table, ddl)` pairs. Parents first; this becomes
  `00_schema.sql`, and `ALL_TABLES` is derived from it.
- `CONTENT_ORDER` — table names in FK-safe insert order. Tables that ship
  empty (the `usage_*` family) are left out.

## Generators — the folder is the data source

| Folder | Source | Cost |
|---|---|---|
| `etl/make/` | values written in the code, or derived from the DB | no API calls |
| `etl/get/` | PokeAPI | ~1,900 calls for a full build |
| `etl/sync/` | championsbattledata.com | accumulates daily |
| `etl/tools/` | — | not part of a build |

Put a new generator in the folder its values come from, not the one named
after what it builds. The listing should answer "what does a rebuild cost?".

`sync/` is the odd one: it is not a build step and never enters `data/sql/`
or `build.py`, because usage snapshots accumulate instead of being rebuilt.

Each module in `make/` and `get/` exposes `TABLE`, `COLUMNS`, and
`build(conn)`. A generator that fills a second table from the same API
response declares `EXTRA = [(table, columns)]` so `dump_sql` knows its
columns. `build(conn)` returns **`INSERT` statements only** — no DDL.
Literal tables build through `parse_utils.literal_build`.
