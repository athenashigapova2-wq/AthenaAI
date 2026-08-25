# Supabase Edge Functions

## Allowed Edge Function responsibilities

Edge Functions must not perform model inference and must never receive an LLM
provider credential. Their allowed scope is deliberately narrow:

- barcode and external food-database lookup;
- Supabase-specific operations that benefit from running next to the database;
- small deterministic data transformations;
- thin authenticated proxies that do not call an LLM provider.

`analyzeFoodProduct` is retained because it performs deterministic
database/OpenFoodFacts work. All AI use cases now use authenticated FastAPI:

- `POST /api/v1/agent/chat` -> Redis/Celery -> LangGraph;
- `POST /api/v1/ai/tasks/{use_case}` -> narrow server-owned AI task;
- `POST /api/v1/nutrition/meal-estimate` -> retrieval-backed meal estimation;
- `POST /api/v1/nutrition/habit-insight` -> deterministic analytics plus insight.

Those paths enter the Python `AIExecutionService`, which applies routing,
privacy, resilience and tracing before the canonical `LLMGateway`.
Provider credentials exist only in the API/worker environment.

## Decommission deployed legacy functions

The source directories have been removed from the repository. Supabase does not
undeploy a function when its local source disappears, so audit and delete any
deployed legacy AI functions explicitly:

```powershell
npx supabase functions list --project-ref <project-ref>
npx supabase functions delete athena-task --project-ref <project-ref>
npx supabase functions delete invoke-llm --project-ref <project-ref>
npx supabase functions delete chat-with-coach --project-ref <project-ref>
npx supabase functions delete analyze-habits --project-ref <project-ref>
npx supabase functions delete estimate-meal --project-ref <project-ref>
```

After deletion, inspect the project's secret names and remove every
provider-specific credential from the Edge runtime. The CI architecture
contract intentionally forbids provider endpoints, credential names and model
completion paths anywhere below `supabase/functions/`, including documentation
and configuration files.
