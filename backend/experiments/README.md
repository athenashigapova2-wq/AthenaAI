# Evaluation experiments

Experiments are server-owned evaluation policies, not frontend A/B switches.
The authenticated user is the assignment unit, so longitudinal conversations
never alternate variants. Assignment is a stable SHA-256 bucket over the
experiment salt, id and user id.

To run an experiment:

1. Copy the example to a version-controlled definition file.
2. Use a stable secret salt and immutable variant ids.
3. Add current per-million-token pricing to each variant when cost comparison
   is required. Missing pricing remains `null`, never guessed.
4. Set `enabled=true` only after offline regression approval.
5. Configure the API and worker with the same values:

```env
EVALUATION_EXPERIMENT_CONFIG_FILE=experiments/agent_quality_v1.json
EVALUATION_EXPERIMENT_ID=agent-quality-v1
```

The API assigns the variant; the client cannot submit `experiment_id` or
`variant_id`. Redis/Celery propagate the assignment and the worker verifies it
against the same definition. `agent_experiment_comparison` compares success,
quality, p50/p95/p99 latency, tokens, estimated cost, retry/fallback, queue and
provider latency by experiment, variant, config hash and route.
