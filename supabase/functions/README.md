# Supabase Edge Functions

## Narrow browser AI tasks

`athena-task` replaces the retired generic `invoke-llm` gateway. Its public
contract accepts only `{ "use_case": "...", "input": { ... } }`. Prompts,
models, output schemas, request limits, and per-user quotas are owned by the
server implementation.

Before deployment:

1. Apply migration `0017_edge_llm_quota.sql`.
2. Set `GIGACHAT_AUTH_KEY` and, for deployed web clients, set
   `ATHENA_ALLOWED_ORIGINS` to a comma-separated exact origin allowlist.
3. Deploy the replacement and remove the already-deployed legacy endpoint:

```powershell
npx supabase db push
npx supabase functions deploy athena-task
npx supabase functions delete invoke-llm
```

Deleting the local source directory alone does not disable an Edge Function
that has already been deployed.
