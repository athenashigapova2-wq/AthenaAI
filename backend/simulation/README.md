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
- legacy answer regexes in `must_include`, `must_not_include`, and
  `expected_facts.answer_patterns`; these are non-blocking diagnostics only.

Evaluation is split into three independent layers:

1. **Hard invariants** are blocking and deterministic: exact route and tool
   boundaries, tool read/write metadata and order, actual in-memory DB facts,
   audited writes, server-validated calories/macros, allergens, and minimum
   calories. They never inspect prose with regex.
   Requests to change calorie targets must finish through the structured
   `submit_calorie_decision` contract. Its result records the action, old and
   proposed targets, enforced minimum, weight-record count, evidence dates, and
   rationale; the same object is returned as `calorie_decision` by the job API.
2. **Semantic quality** is an optional schema-based judge with four 1–5 rubric
   dimensions: factual consistency, personalization, longitudinal reasoning,
   and usefulness. Enable it only for an intentional live run with
   `ATHENA_RUN_SEMANTIC_JUDGE=1`.
3. **Human gold** is the separately versioned, named-reviewer subset in
   `backend/simulation/gold/human_reviewed.json`. Generated judgments are never
   promoted to human gold automatically.

Gold candidates that share a `scenario_id` and `checkpoint_id` with a fixture
are injected into the semantic judge payload without exposing the reference
answer. Their curated rubric and per-dimension minimum scores are applied to the
result. Every live report includes `gold_fixture_coverage`: candidates without a
fixture are listed as `standalone_not_executed`, so they cannot be mistaken for
executed checkpoints. A material prompt mismatch stops the live evaluator before
any provider request.

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
$env:ATHENA_RUN_SEMANTIC_JUDGE = "1" # optional: one extra judged call/checkpoint
$env:ATHENA_LIVE_SCENARIOS = "anna_14d_v1"
$env:ATHENA_LIVE_CHECKPOINTS = "anna_d7_t1,anna_d14_t1" # optional
python -m pytest tests/live_evals --run-live-evals -q
# Or generate JSON and Markdown in the same deliberately opted-in session:
python backend/scripts/eval_longitudinal_quality.py `
  --report-dir backend/simulation/reports/generated
Remove-Item Env:ATHENA_RUN_SEMANTIC_JUDGE -ErrorAction SilentlyContinue
```

The scheduled/manual GitHub workflow accepts the same comma-separated scenario
and checkpoint lists. Scenario data remains in memory and RAG is disabled; only
the provider calls are live.
