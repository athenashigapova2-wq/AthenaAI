# Supabase Edge Functions

## Narrow browser AI tasks

`athena-task` replaces the retired generic `invoke-llm` gateway. Its public
contract accepts only `{ "use_case": "...", "input": { ... } }`. Prompts,
models, output schemas, request limits, and per-user quotas are owned by the
server implementation.

This is the only public browser-to-LLM Edge Function. Agent chat, tools,
conversation memory, and longitudinal reasoning use the canonical
FastAPI -> Redis/Celery -> backend LLM path. `analyzeFoodProduct` is retained
because it performs deterministic database/OpenFoodFacts work and does not call
an LLM.

Legacy LLM functions must not be deployed: `invoke-llm`, `chat-with-coach`,
`analyze-habits`, and `estimate-meal`.

`estimate-meal` is replaced by the retrieval-backed Python
`MealEstimationService` (`POST /api/v1/nutrition/meal-estimate`). Its parsing and
reranking stages use the canonical routed LLM gateway; candidate retrieval and
macro calculation are deterministic. `analyze-habits` is replaced by
`HabitAnalyticsService` plus `HabitInsightGenerator`
(`POST /api/v1/nutrition/habit-insight`).

Before deployment:

1. Apply migration `0017_edge_llm_quota.sql`.
2. Set `GIGACHAT_AUTH_KEY` and, for deployed web clients, set
   `ATHENA_ALLOWED_ORIGINS` to a comma-separated exact origin allowlist.
3. Deploy the replacement and remove the already-deployed legacy endpoint:

```powershell
npx supabase db push
npx supabase functions deploy athena-task
npx supabase functions delete invoke-llm
npx supabase functions delete chat-with-coach
npx supabase functions delete analyze-habits
npx supabase functions delete estimate-meal
```

Deleting the local source directory alone does not disable an Edge Function
that has already been deployed.
