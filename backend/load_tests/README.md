# Athena agent load tests

The suite measures the authenticated Redis/Celery chat path, not the Vite UI:

- `POST agent/chat enqueue [stage]`: API validation and Redis enqueue latency;
- `GET agent/chat/jobs/{job_id} poll [stage]`: job-store availability under load;
- `FLOW agent_chat_e2e [stage]`: end-to-end latency from enqueue to completed answer.

Locust reports RPS, error percentage and response-time percentiles, including p50,
p95 and p99. Stage-specific names make overload and recovery visible separately.

## Safety

This suite makes real GigaChat calls and writes conversations, messages and traces.
Run it against a dedicated local/staging Supabase project and dedicated test users,
never against production. Access tokens are secrets: keep the token file outside the
repository and do not paste it into logs or commits.

## Install

From the repository root with `.venv` activated:

```powershell
python -m pip install -r .\backend\requirements-load.txt
```

## Authentication

For a smoke test, provide one current Supabase access token:

```powershell
$env:LOAD_TEST_ACCESS_TOKEN = "<dedicated-test-user-access-token>"
$env:LOAD_TEST_ACKNOWLEDGE_PROVIDER_COSTS = "true"
```

For real parallel users, create a JSON file outside the repository with one token
per dedicated test account:

```json
[
  "first-access-token",
  "second-access-token"
]
```

Then set its path:

```powershell
$env:LOAD_TEST_TOKEN_FILE = "C:\secure\athena-load-tokens.json"
$env:LOAD_TEST_ACKNOWLEDGE_PROVIDER_COSTS = "true"
```

If there are fewer tokens than virtual users, tokens are reused and Locust emits a
warning. Concurrency is still real, but user-level isolation is only realistic with
one token per virtual user.

## Default staged run

The default profile is deliberately small:

| Stage | Duration | Users | Spawn rate |
|---|---:|---:|---:|
| warmup | 30 s | 2 | 1/s |
| steady | 90 s | 4 | 1/s |
| overload | 90 s | 12 | 4/s |
| recovery | 60 s | 4 | 4/s |

The overload stage exceeds the default four-thread worker concurrency. It should
increase queue/end-to-end latency without making enqueue unavailable; the recovery
stage shows whether latency and errors return to their steady-state range.

Create a report directory and run headlessly:

```powershell
$loadReportDir = Join-Path $env:TEMP "athena-load"
New-Item -ItemType Directory -Force -Path $loadReportDir | Out-Null

python -m locust `
  -f .\backend\load_tests\locustfile.py `
  --headless `
  --host "http://127.0.0.1:8001" `
  --csv "$loadReportDir\agent" `
  --csv-full-history `
  --html "$loadReportDir\report.html" `
  --only-summary
```

Locust stops automatically after the final stage. The important files are:

- `agent_stats.csv`: p50/p95/p99, RPS and failures per stage;
- `agent_stats_history.csv`: time series during ramp and overload;
- `agent_failures.csv`: grouped failure causes;
- `report.html`: interactive report.

Open the report:

```powershell
Start-Process "$loadReportDir\report.html"
```

## SLO check

By default, only `steady` and `recovery` are asserted. Overload is diagnostic: it is
allowed to degrade, but recovery must return below the thresholds.

```powershell
python .\backend\load_tests\analyze_results.py `
  "$loadReportDir\agent_stats.csv" `
  --json "$loadReportDir\summary.json"
```

Default thresholds:

- error rate <= 5%;
- p95 <= 30,000 ms;
- p99 <= 60,000 ms.

Override them when a measured baseline is available:

```powershell
$env:LOAD_TEST_MAX_ERROR_PERCENT = "2"
$env:LOAD_TEST_MAX_P95_MS = "20000"
$env:LOAD_TEST_MAX_P99_MS = "45000"
```

## Custom stages

`duration_seconds` is the duration of each stage, not cumulative time:

```powershell
$env:LOAD_TEST_STAGES = '[{"name":"warmup","duration_seconds":30,"users":2,"spawn_rate":1},{"name":"steady","duration_seconds":120,"users":4,"spawn_rate":1},{"name":"overload","duration_seconds":180,"users":20,"spawn_rate":5},{"name":"recovery","duration_seconds":120,"users":4,"spawn_rate":5}]'
```

Other controls:

- `LOAD_TEST_PROMPTS`: JSON string array of safe read-only prompts;
- `LOAD_TEST_LOCALE`: `ru`, `en`, `fr`, `es` or `zh`;
- `LOAD_TEST_MAX_JOB_WAIT_SECONDS`: end-to-end timeout, default 180;
- `LOAD_TEST_POLL_INTERVAL_SECONDS`: status polling interval, default 0.75;
- `LOAD_TEST_TURNS_PER_CONVERSATION`: rotate conversation after N turns, default 3;
- `LOAD_TEST_MIN_THINK_SECONDS` / `LOAD_TEST_MAX_THINK_SECONDS`: pause between flows.

During the run, observe the system from another terminal:

```powershell
docker stats athenaai-api-1 athenaai-worker-1 athenaai-redis-1
docker compose logs -f --tail=50 api worker
```

Healthy overload behavior is: enqueue remains fast, jobs queue instead of being
lost, error rate stays bounded, and recovery returns toward steady-state p95/p99.
