# Pokemon Champions

Pokemon Champions (Regulation M-B) battle helper. Korean-language project:
code comments, commit messages, and docs are Korean. Keep them Korean.

## Where does a new file go?

Ask in order. Stop at the first "yes".

| | Question | Folder |
|---|---|---|
| 1 | Run by hand, occasionally? | `scripts/` |
| 2 | Touches `print` / `input` / HTTP responses? | `interfaces/` |
| 3 | A tool the LLM calls? | `agent/` |
| 4 | Contains a SQL string? | `db/repositories/` |
| 5 | Takes a conn, file, or network? | `usecases/` |
| 6 | Same input always gives same output? | `calc/` |
| 7 | Just the shape of data? | `domain/` |

The test is the signature, not the file contents. `conn` in the parameter
list means `usecases/`. No `conn` means `calc/`.

## Hard rules

- Dependencies flow one way: `interfaces` -> `usecases` -> `db.repositories`.
  `usecases` also calls `calc`. `domain` imports nothing from this project.
- `scripts/` may import `src/`. **`src/` must never import `scripts/`.**
  `pyproject.toml` (`where = ["src"]`) enforces this — `scripts/` is not installed.
- Regulation constants (level 50, IV 31, SP 66) live only in `config.py`.
- Never create an empty folder or a placeholder file. Add it when it has content.

## Commands

```bash
python -m scripts.etl.load_sql   # set up the DB from data/sql/ (seconds, no API)
pytest                            # 103 tests; 93 need no DB
python main.py                    # CLI
python web.py                     # http://127.0.0.1:8000
```

Do **not** run `scripts.etl.build` casually — it makes ~1,900 PokeAPI calls
and requires an empty DB.

## Commits

- Never mix a refactor with a feature. One kind of risk per commit.
- Korean subject line, imperative, stating what changed and why.
- After changing a response shape, re-record goldens and **read the diff**:
  `UPDATE_GOLDEN=1 pytest tests/test_api.py tests/test_tools.py`
  Accepting a golden diff without reading it makes the test worthless.
