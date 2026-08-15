# agent/ — the LLM helper

The model picks tools. **The model does not calculate.**

## Hard rules

- No arithmetic in a tool. `calc_damage`, `power_index`, `bulk_index` call the
  same-named functions in `calc/` (through `usecases/battle.py`) with arguments
  swapped in. None of the 15 tools computes anything itself.
- No SQL. Lookup tools call `db/repositories/`; anything needing assembly goes
  through `usecases/`.
- Tools return `{"error": "..."}` rather than raising. The runner feeds the
  result straight back to the model, and a traceback is useless to it.
- Keep error wording identical across tools. The same failure phrased two ways
  reads to the model as two different events.

## A tool's job is naming, not logic

Resolve the Korean name to a DB row, call the layer below, put Korean names
back on the result. If a tool is doing more than that, the logic belongs in
`usecases/`.

## Adding a tool

1. Function in `tools.py`, schema in `schemas.TOOLS`, register in `tools.HANDLERS`.
2. Add at least one case to `CALLS` in `tests/test_tools.py` — a separate test
   fails if any tool is missing from that list, because an untested tool is
   unguarded.
3. Re-record and read the diff:
   `UPDATE_GOLDEN=1 pytest tests/test_tools.py`

## Do not put the type-name table in the prompt

`runner.py` reads it from `pokemon_type_names` at startup. Hardcoding it makes
a second copy that drifts when the DB spelling changes.
