# interfaces/ — the only place print / input / HTTP may appear

`cli.py` for the terminal, `api/` for the web. Both call the same
`usecases/` functions and only differ in how they shape the result.

## Hard rules

- **Do not calculate.** No damage formula, no stat math, no default-filling.
  If a route computes something, that logic belongs in `usecases/`.
- **Do not query.** No SQL, no repository calls that reassemble a result —
  go through `usecases/`.
- Adapter concerns stop here: HTTP status codes, Pydantic models, icon URLs,
  terminal column widths.

## Routes stay thin

A route should read as: parse request -> call one `usecases/` function ->
hand the result to `views.py`. If a route body is mostly a dict literal, that
dict belongs in `views.py`.

`app.py` grew to 833 lines this way — 13 of its 18 helpers were row-to-JSON
shaping, and one route was 60 lines of dict literal around a single call.

## Error mapping is this layer's job

`usecases/` raises `ValueError` and returns `None`; deciding whether that is a
400 or a 404 is an adapter decision. Keep it here, not in `usecases/`.

## After changing a response shape

```bash
UPDATE_GOLDEN=1 pytest tests/test_api.py
```

Then read the diff. `tests/golden/api.json` pins 16 route responses whole, so
an unintended field change shows up immediately — but only if you look.
