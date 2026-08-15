# calc/ — pure calculation only

## Hard rules

- **No `conn` parameter.** Nothing here touches the database.
- No file or network I/O. No `print()`, no `input()`.
- Same input MUST always produce the same output.
- Do not import from `usecases/`, `interfaces/`, or `agent/`.

If a function here needs a `conn`, it belongs in `usecases/`. Move it
rather than adding the parameter.

## Getting DB data in

Take it as an argument. The caller in `usecases/` does the fetching.

- Reference tables (type chart, weather, terrain, status) arrive as `rules: Rules`.
- Everything here takes `BattlePokemon`, never the plain `Pokemon`.
  A roster entry has no HP, stat stages, or status; passing one in used
  to compute silently at full HP with no boosts. Now it raises.
- Split battle state by **who it applies to**, never by anything else.
  Per-pokemon (HP, stat stages, status, grounded) -> `BattlePokemon`.
  Field-wide (weather, terrain, crit, screens, doubles) -> `ctx`.
  Never store the same fact in both — that bug existed and cost a
  silently-wrong result, not an exception.

## Adding a mechanic

- Ability / item multipliers -> `modifiers.py`, as 4096-based integers (4096 = 1.0).
- End-of-turn HP changes -> `residual.py`. Fractions come from the DB via
  `Rules.conditions`, not hardcoded here.
- Table keys are Korean names. A typo does not raise — it silently yields
  "no modifier applied".

Verify against known game values: `python -m scripts.check_damage`
