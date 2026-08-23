# Longitudinal simulation contour

This contour replays fictional user history over simulated calendar time.
Its first fixture is derived from the workbook sheets `profiles`, `timeline`,
`conversations`, and `expectations`.

## What the first offline run validates

- all profile anchors satisfy the backend profile contract;
- generated profile variants are reproducible for a fixed random seed;
- timeline events become visible only after their simulated timestamp;
- `date.today()` based nutrition, recovery, and workout windows follow
  `freezegun` time;
- the full LangGraph path runs with `LLM_PROVIDER=mock` and never contacts
  GigaChat.

The deterministic mock does **not** measure answer quality and intentionally
does not call tools. `must_include`, `must_not_include`, and expected-tool
rubrics are retained in the fixture for a later GigaChat/evaluator run.

## Run

```powershell
python -m pip install -r .\backend\requirements-test.txt
python .\backend\scripts\test_longitudinal_simulation.py
```

The test uses an in-memory Supabase substitute, so it cannot change real user
data.
