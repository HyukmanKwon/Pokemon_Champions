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
- Nothing lives here that does not participate in serving the app. A tool you
  would run once and forget belongs in the commit message, not the tree.

## What is here

| | What |
|---|---|
| `etl/` | the database — build it, load it, dump it, keep usage flowing |
| `chat.py` | talk to the helper from a terminal. The LLM path |
| `make_type_icons.py` | redraw type badges in Korean |
| `daily_usage.sh` + `.plist` | launchd job that runs `sync_usage` daily |

`make_type_icons.py` looks like a one-off but is not. `data/images/` is
gitignored and `assets.type_icon()` returns `None` rather than drawing, so
this script is the only way a fresh clone gets Korean type badges. Deleting
it silently drops every badge to a 404.

## etl/ — three directions, do not confuse them

| | When | What |
|---|---|---|
| `load_sql.py` | every install | `data/sql/` -> DB. No API calls, seconds |
| `build.py` | new regulation | PokeAPI -> DB. ~1,900 calls, minutes |
| `dump_sql.py` | after editing the DB | DB -> `data/sql/`, then commit |

`build.py` needs an empty DB and always re-fetches. **It does not write
`data/sql/`** — only `dump_sql.py` does. Do not run `build.py` to "fix" a
database; fix it in psql and dump.

`data/sql/` is two files and is the only home for values a rebuild cannot
reproduce — Korean names PokeAPI does not have, move flags its CSV does not
cover. There is no second copy; `data/overrides/` used to be one and was
removed because keeping two in sync was the only work it created.

| | From | What |
|---|---|---|
| `00_schema.sql` | `schema.py` | every `CREATE TYPE` / `CREATE TABLE`, parents first |
| `01_content.sql` | the live DB | every `INSERT`, in FK-safe order |

After any change that alters DB contents, run `dump_sql.py` and commit the
result, or a rebuild will not match your database.

`sync_usage.py` is the exception: usage snapshots accumulate daily and are
**not** part of `data/sql/`. `daily_usage.sh` runs it under launchd.
Always use `--live` and `--backfill`, never "today only" — a missed day is
gone once the source drops it. Already-fetched dates are skipped, so running
it daily costs nothing.

`--since` defaults to `SEASON_START` in `sync_usage.py`. The source's folder
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

INSERT assembly (`sql_of`, `to_values`) lives here too. Both `pokeapi.py` and
`build.py` need it, and `build.py` already imports `pokeapi.py`, so putting it
in either one would make the two import each other.

## The file name says where the values come from

| File | Source | Cost |
|---|---|---|
| `build.py` | values written in the code, or derived from the DB | no API calls |
| `pokeapi.py` | PokeAPI | ~1,900 calls for a full build |
| `sync_usage.py` | championsbattledata.com | accumulates daily |

Put a new generator in the file its values come from, not the one named after
what it builds. A reader should be able to answer "what does a rebuild cost?"
from the listing alone.

`sync_usage.py` is the odd one: it is not a build step and never enters
`data/sql/` or `build.py`, because usage snapshots accumulate instead of
being rebuilt.

`build.py` drives everything through `STEPS`, a list of `Step(name, table,
columns, build, extra)`. `build` returns **`INSERT` statements only** — no
DDL. A step that fills a second table from the same API response lists it in
`extra` so `dump_sql` knows its columns.
