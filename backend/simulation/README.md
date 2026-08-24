# Longitudinal simulation contour

The contour discovers every `backend/simulation/fixtures/*_<N>d.json` fixture
where `N` is between 14 and 30 (including `*_14d.json` and `*_30d.json`).
`profiles.json` remains the shared fictional-persona catalogue and is not
treated as a scenario.

Each checkpoint may declare:

- `expected_route`, `expected_tools`, and `forbidden_tools`;
- `expected_facts` from frozen profile, weight, intake, and workout state;
- `nutrition` targets and macro/calorie consistency tolerance;
- `safety` limits and required evidence before calorie changes;
- answer regexes in `must_include`, `must_not_include`, and
  `expected_facts.answer_patterns` for the live evaluator.

## Offline suite

The offline suite uses `freezegun`, in-memory Supabase data, and the deterministic
mock LLM. It checks routing, tool boundaries, facts, nutrition/safety contracts,
and orchestration without contacting GigaChat.

```powershell
python -m pytest tests/simulation -q
python backend/scripts/test_longitudinal_simulation.py `
  --report-dir backend/simulation/reports/generated
```

Select one or more scenarios by scenario id, persona id, filename, or stem:

```powershell
$env:ATHENA_SIMULATION_SCENARIOS = "anna_14d_v1"
python -m pytest tests/simulation -q
Remove-Item Env:ATHENA_SIMULATION_SCENARIOS
```

The script writes both JSON and Markdown when `--report-dir` is supplied.
Generated reports are ignored by Git; copy a reviewed baseline into the parent
`reports` directory only when it should become repository history.

## Live GigaChat suite (explicit opt-in only)

Normal pytest and CI never run real GigaChat evaluations. A live run requires
all three deliberate choices: selecting `tests/live_evals`, passing
`--run-live-evals`, and setting `ATHENA_RUN_LIVE_EVALS=1`.

```powershell
$env:ATHENA_RUN_LIVE_EVALS = "1"
$env:ATHENA_LIVE_SCENARIOS = "anna_14d_v1"
$env:ATHENA_LIVE_CHECKPOINTS = "anna_d7_t1,anna_d14_t1" # optional
python -m pytest tests/live_evals --run-live-evals -q
# Or generate JSON and Markdown in the same deliberately opted-in session:
python backend/scripts/eval_longitudinal_quality.py `
  --report-dir backend/simulation/reports/generated
```

The scheduled/manual GitHub workflow accepts the same comma-separated scenario
and checkpoint lists. Scenario data remains in memory and RAG is disabled; only
the provider calls are live.
