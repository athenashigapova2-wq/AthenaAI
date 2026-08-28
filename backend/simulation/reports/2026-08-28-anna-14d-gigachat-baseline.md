# Anna 14-day GigaChat baseline

Date: 2026-08-28

Branch: `main`

Base commit: `57f8f10` (`fix: repair OCR CI contracts`)

Working tree: includes the read-only test food database integration listed in
this baseline; these changes were not committed at evaluation time.

Scenario: `anna_14d_v1`

Provider/model: `gigachat` / `GigaChat-2`

RAG: disabled

Semantic judge: enabled

Food database: committed read-only snapshot, 21 exact `food_nutrients` rows

Remote Supabase reads/writes: `0 / 0`

## Result

- Scenario: **passed**.
- Hard invariants: **3/3 checkpoints passed**.
- Semantic quality: **3/3 checkpoints passed**.
- Gold candidates: **3/3 passed**.
- Human gold review: pending; model-as-judge scores are not a substitute for it.

| Checkpoint | Route | Required tools | Hard | Factual | Personalization | Longitudinal | Usefulness | Mean |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `anna_d0_t1` daily plan | `nutrition` | `get_my_profile`, `get_daily_intake`, `submit_daily_nutrition_plan` | pass | 5 | 4 | 3 | 4 | 4.00 |
| `anna_d7_t1` weekly progress | `recovery` | `get_weight_trend` | pass | 5 | 4 | 5 | 4 | 4.50 |
| `anna_d14_t1` calorie decision | `nutrition` | `get_my_profile`, `get_weight_trend`, `submit_calorie_decision` | pass | 5 | 5 | 5 | 4 | 4.75 |

## Grounded nutrition evidence

The day-0 plan was recalculated by the server from exact rows in the test food
database. It contained 13 unique products and passed allergy, minimum portion,
macro consistency, minimum calorie, and server-validation checks.

- Validated total: `1749.2 kcal`, `130.0 g` protein, `48.9 g` fat,
  `197.0 g` carbohydrates.
- Target: `1750 kcal`, `130 g` protein, `49 g` fat, `197 g` carbohydrates.
- Allergen check for Anna's peanut allergy: passed.
- Food diversity score: `100/100`.

## Longitudinal and calorie evidence

- Day 7: the answer used two actual measurements and reported `-0.6 kg`.
- Day 14: `get_weight_trend` ran before the calorie decision and used three
  measurements from `2026-09-01` through `2026-09-15` (`-1.1 kg`).
- Structured calorie decision: `keep`, `1750 -> 1750 kcal`; the `1200 kcal`
  safety minimum was respected.

## Interpretation

This is a valid baseline for the current model and deterministic application
policies, not proof of general quality. The weakest semantic dimension was the
day-0 longitudinal score (`3/5`), which is expected because the first checkpoint
has no prior history. Usefulness remained `4/5` at all checkpoints, leaving room
for more actionable next-step guidance. The next comparison should use the same
fixture, food snapshot, model, and rubric, followed by human review.

Full machine-readable evidence:
`longitudinal-live-20260828T115327Z.json`.
