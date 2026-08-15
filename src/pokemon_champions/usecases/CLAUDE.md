# usecases/ — assembly layer

Fetch from the outside (DB, files, network), fill in defaults, call `calc/`.
This is the only layer that knows both where data comes from and how the
calculators want it.

## Hard rules

- **Return domain objects, not view models.** `Pokemon`, `DamageRange`, `Shot`
  — never JSON-ready dicts. Each adapter shapes the same result differently:
  the API adds icon URLs, the LLM tools add `ko_name` pairs, the CLI prints
  a line. Calculate once, shape three times.
- Do not import from `interfaces/` or `agent/`.
- No `print()` / `input()`. Return values; the layer above decides output.
- **No SQL.** Call `db/repositories/`.
- `conn` is always the first parameter, never module-level state — concurrent
  web requests would share one psycopg2 connection. (Caching reference *data*
  at module level is fine; caching the connection is not.)

## This layer must not know about

HTTP status codes · Pydantic models · LLM tool JSON schemas · the
`{"error": ...}` convention · icon URLs.

If any of those appear here, it has become an adapter again.

## Exception worth knowing

`roster.py` takes no `conn`. Decks live in a file, not the DB, because the
ETL rebuilds the whole reference database and would take the decks with it.
It still touches the outside world, so it still belongs here.
