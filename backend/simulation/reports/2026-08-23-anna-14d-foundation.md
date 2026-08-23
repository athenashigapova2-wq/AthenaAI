# Anna 14-day longitudinal foundation baseline

Date: 2026-08-23

Source workbook: `симуляционные тестироания.xlsx`

## Contour

- 12 normalized anchor profiles from `profiles`;
- 24 deterministic generated variants (`seed=42`);
- one complete 14-day scenario for `vp_anna_01`;
- frozen timestamps in `Europe/Moscow`;
- in-memory Supabase substitute;
- `LLM_PROVIDER=mock`, RAG disabled;
- no GigaChat or remote Supabase calls.

## Foundation results

| Check | Result |
|---|---:|
| Anchor profile schema | passed, 12/12 |
| Generated profile reproducibility | passed, 24/24 |
| Day 1 meal visibility | 1 meal |
| Day 7 weight trend | -0.6 kg |
| Day 7 workout window | 1 workout |
| Day 14 weight trend | -1.1 kg |
| Conversation history | 3 turns / 6 messages |
| External LLM calls | 0 |

## Source normalization

- renamed the second `vp_anna_01` row to `vp_anna_02`;
- normalized `meduim` to `medium`;
- normalized `youghurt` / `youghurts` and `asparugus` spelling;
- derived required `fat_target_g` and `carb_target_g` values because the
  workbook does not provide them.

The original workbook was not modified. Each normalized profile retains its
source persona id and source row.

## Quality-readiness observations

Answer quality was not measured. The infrastructure mock intentionally returns
a fixed response and never calls tools. Its deterministic routes currently
leave these expected tools unavailable:

| Checkpoint | Mock route | Missing expected tool |
|---|---|---|
| `anna_d0_t1` | `general` | `get_my_profile` |
| `anna_d7_t1` | `general` | `get_weight_trend` |
| `anna_d14_t1` | `nutrition` | `get_weight_trend` |

These are inputs for the next stage: a scenario-aware tool-selection/evaluation
contour. They are not evidence that production GigaChat produces the same
routes.
