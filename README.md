# Athena AI

Athena is a multilingual nutrition and fitness coaching application. It combines
a React client, a FastAPI backend, background jobs, a nutrition knowledge base,
and guarded model calls. The repository also contains deterministic tests,
longitudinal simulations, load tests, and an OCR evaluation pipeline.

This is an engineering project, not a medical device. Nutrition and training
recommendations should not replace advice from a qualified professional.

## What the project does

Athena lets an authenticated user:

- chat with a nutrition, workout, recovery, or general coach;
- log meals, workouts, health observations, and weight measurements;
- receive meal plans checked against calories, macros, allergies, dietary
  restrictions, disliked foods, budget, and feasible portions;
- review progress across multiple dates before changing calorie targets;
- stream background-job progress and cancel an active request;
- confirm state-changing tool calls before they execute;
- estimate meal nutrition and extract structured receipt or invoice data;
- export or delete trace data and permanently delete an account.

The web client supports English, Russian, French, Spanish, and Chinese. The
repository also includes an Android project for building an APK against an HTTPS
backend.

## Why the project is useful

Athena demonstrates how a model-backed product can keep important decisions in
ordinary application code. The model may interpret a request or draft an answer,
but the server owns authentication, data access, tool permissions, nutrition
checks, write confirmation, idempotency, retries, rate limiting, trace redaction,
and account deletion.

The project can be used as:

- a reference for FastAPI, Redis, Celery, React, and Supabase integration;
- an example of deterministic checks around probabilistic output;
- a test bed for offline evaluation, longitudinal scenarios, and load testing;
- a portfolio project supported by code, tests, and committed baseline reports.

## Verified examples and figures

These are recorded baselines with specific test conditions, not general
performance claims.

### Load-test baseline

The committed JMeter baseline used five virtual users, five iterations per user,
and a 30-second ramp-up against the local Docker stack with the real GigaChat
provider.

| Metric | Result |
| --- | ---: |
| Completed scenarios | 25 / 25 |
| Error rate | 0% |
| Test duration | 39.345 s |
| End-to-end throughput | 0.635 scenarios/s |
| End-to-end p50 | 3.068 s |
| End-to-end p95 | 5.145 s |
| End-to-end p99 / maximum | 7.389 s |

The method, environment, and calculations are recorded in
[`backend/load_tests/reports/2026-08-21-baseline-5x5.md`](backend/load_tests/reports/2026-08-21-baseline-5x5.md).
An earlier unsuccessful run remains beside it as historical evidence.

### Longitudinal quality baseline

The committed Anna 14-day live baseline contains three checkpoints. All three
passed their hard invariants and semantic thresholds. The day-zero plan used 13
unique products and was recalculated as 1,749.2 kcal against a 1,750 kcal target.
Human review is explicitly marked as pending.

See
[`backend/simulation/reports/2026-08-28-anna-14d-gigachat-baseline.md`](backend/simulation/reports/2026-08-28-anna-14d-gigachat-baseline.md)
for the full evidence and limitations.

## How users can get started with the project

### Requirements

- Git;
- Node.js 22 and npm;
- Python 3.11;
- Docker Desktop with Linux containers;
- a Supabase project;
- a GigaChat credential only for intentional live-provider runs.

### 1. Clone and install

```powershell
git clone https://github.com/athenashigapova2-wq/AthenaAI.git
cd AthenaAI
npm ci
python -m venv .venv
& ".\.venv\Scripts\Activate.ps1"
python -m pip install -r ".\backend\requirements-dev.txt"
```

### 2. Configure local environment files

```powershell
Copy-Item .env.example .env
Copy-Item backend/.env.example backend/.env
Copy-Item observability/.env.example observability/.env
```

Frontend `.env` example:

```dotenv
VITE_SUPABASE_URL=https://your-project.supabase.co
VITE_SUPABASE_ANON_KEY=your-public-anon-key
VITE_AGENT_API_URL=http://127.0.0.1:8001
AGENT_PROXY_TARGET=http://127.0.0.1:8001
```

Backend `backend/.env` example:

```dotenv
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_ROLE_KEY=your-server-only-service-role-key
LLM_PROVIDER=mock
APP_ENV=dev
TRACE_CONTENT_MODE=off
```

`LLM_PROVIDER=mock` is the safest first run. It exercises the application path
without calling an external model and does not bypass JWT validation. For an
intentional GigaChat run, set `LLM_PROVIDER=gigachat` and keep
`GIGACHAT_AUTH_KEY` only in `backend/.env` or a deployment secret store. Never
put service-role or provider credentials in `VITE_*` variables.

Replace the placeholder Grafana and InfluxDB credentials in
`observability/.env`.

### 3. Apply Supabase migrations

```powershell
npx supabase login
npx supabase link --project-ref <your-project-ref>
npx supabase db push
```

Migrations are versioned in `supabase/migrations/`. Review them before applying
them to a non-development project.

### 4. Start the backend

```powershell
docker compose up -d --build
docker compose ps
```

| Service | Purpose | Local address |
| --- | --- | --- |
| `api` | FastAPI HTTP and authentication boundary | `http://127.0.0.1:8001` |
| `worker` | Celery background execution | internal only |
| `redis` | broker and short-lived job state | `127.0.0.1:6379` |
| `influxdb` | JMeter metrics | `http://127.0.0.1:8086` |
| `grafana` | load-test dashboards | `http://127.0.0.1:3000` |

Check readiness and logs:

```powershell
Invoke-RestMethod "http://127.0.0.1:8001/health"
Invoke-RestMethod "http://127.0.0.1:8001/health/ready"
docker compose logs -f api worker
```

The worker may remain in `health: starting` while its local embedding model is
downloaded for the first time.

### 5. Start the web client

```powershell
npm run dev -- --host 127.0.0.1 --port 5175
```

Open `http://127.0.0.1:5175`, register or sign in through Supabase, and send a
message. With the mock provider, a successful response begins with text similar
to:

```text
[MOCK:general] Deterministic test response. No external LLM was called.
```

### API example

The chat endpoint returns HTTP 202 with a job identifier. The client then uses
SSE or the status endpoint until the job reaches a terminal state.

```powershell
$headers = @{
    Authorization = "Bearer $env:LOAD_TEST_ACCESS_TOKEN"
    "Content-Type" = "application/json"
}
$body = @{ message = "Show my progress"; locale = "en" } | ConvertTo-Json

$job = Invoke-RestMethod `
    -Method Post `
    -Uri "http://127.0.0.1:8001/api/v1/agent/chat" `
    -Headers $headers `
    -Body $body

Invoke-RestMethod `
    -Uri "http://127.0.0.1:8001/api/v1/agent/chat/jobs/$($job.job_id)" `
    -Headers $headers
```

The token must belong to the user whose data is requested. Missing and foreign
job identifiers intentionally produce the same response so ownership is not
leaked.

## Tests and reproducible evaluation

Backend and offline checks:

```powershell
python -m ruff check backend/app tests
python -m mypy
python -m pytest tests/unit tests/integration tests/evals tests/simulation -q
```

Frontend checks:

```powershell
npm run lint
npm run typecheck:ci
npm run test:ui
npm run build
```

Browser tests require Playwright Chromium:

```powershell
npx playwright install chromium
npm run test:e2e
```

The browser suite covers login and onboarding, chat, meal logging, expired JWTs,
worker failures, duplicate submissions, conversation switching, mobile layout,
and accessibility. The write-confirmation browser case is currently skipped and
must not be counted as passing coverage.

The default pytest configuration never runs a real provider. Offline longitudinal
scenarios use frozen dates, in-memory data, and the deterministic mock:

```powershell
python backend/scripts/test_longitudinal_simulation.py `
    --report-dir backend/simulation/reports/generated
```

Select one scenario while debugging:

```powershell
$env:ATHENA_SIMULATION_SCENARIOS = "anna_14d_v1"
python -m pytest tests/simulation -q
Remove-Item Env:ATHENA_SIMULATION_SCENARIOS
```

Live evaluation requires separate explicit flags and a dedicated test path. See
[`backend/simulation/README.md`](backend/simulation/README.md).

### JMeter and Grafana

```powershell
$env:LOAD_TEST_ACCESS_TOKEN = "<fresh Supabase access token>"
.\backend\load_tests\jmeter\run-smoke-with-grafana.ps1 `
    -Scenario "baseline-check"
```

Open `http://127.0.0.1:3000/d/athena-jmeter-load-tests` and select the generated
run. JTL files are the authoritative full-run source; Grafana displays
five-second interval aggregates.

### Receipt and invoice OCR

The OCR pipeline accepts bounded PDF or image uploads, performs extraction,
schema and cross-field validation, calculates confidence, and flags uncertain
output for review. Evaluation data and commands are in
[`backend/evaluation/document_ocr/README.md`](backend/evaluation/document_ocr/README.md).
AWS Textract and live normalization are disabled by default and may incur cost
when deliberately enabled.

## Android APK

The packaged Android application requires an HTTPS backend:

```powershell
$env:VITE_AGENT_API_URL = "https://api.example.com"
npm run android:apk
```

The build script rejects cleartext backend URLs. Configuration is in
`capacitor.config.ts`; the native project is in `android/`.

## Project structure

```text
backend/app/                 FastAPI application and services
backend/app/agents/          routing and specialist execution
backend/app/ai_execution/    provider invocation policies
backend/app/document_ocr/    document extraction and validation
backend/app/tools/           authenticated read and write tools
backend/app/workers/         Celery configuration and tasks
backend/load_tests/          JMeter scripts and committed baselines
backend/simulation/          longitudinal fixtures and evaluation
e2e/                         Playwright critical-flow tests
observability/               InfluxDB and Grafana configuration
src/                         React application
supabase/migrations/         database and row-level-security migrations
tests/                       unit, integration, evaluation, and simulation tests
```

## Security and privacy notes

- Identity comes from a validated Supabase JWT, not from request payloads.
- Jobs, conversations, traces, and write confirmations are owner-scoped.
- State-changing tools require confirmation and an idempotency key.
- TLS certificate verification remains enabled for provider calls.
- `TRACE_CONTENT_MODE=off` is the production-safe default.
- OCR source bytes are processed in memory and are not persisted automatically.
- Secrets belong in ignored local files or deployment secret stores.

Do not commit real medical documents, credentials, access tokens, or personal
conversations to fixtures or reports.

## Where users can get help with the project

Start with:

- [`backend/WORKERS.md`](backend/WORKERS.md) for Redis and Celery diagnostics;
- [`backend/simulation/README.md`](backend/simulation/README.md) for longitudinal
  tests and live-evaluation safeguards;
- [`tests/README.md`](tests/README.md) for test-suite boundaries;
- [`backend/evaluation/document_ocr/README.md`](backend/evaluation/document_ocr/README.md)
  for OCR evaluation.

For reproducible bugs or questions, open a
[GitHub issue](https://github.com/athenashigapova2-wq/AthenaAI/issues) with the
command, expected and actual result, redacted logs, operating system, and relevant
tool versions. Never post tokens, service-role keys, provider credentials, or raw
user content.

## Who maintains and contributes to the project

Athena AI is maintained by
[`@athenashigapova2-wq`](https://github.com/athenashigapova2-wq). Git history is
the source of truth for individual contributions.

Contributions should be small and reviewable:

1. create a branch from `main`;
2. add or update focused tests;
3. run the relevant backend and frontend checks;
4. avoid committing secrets, generated reports, local databases, or builds;
5. open a pull request explaining the problem, smallest fix, and verification.

Security-sensitive reports should be shared privately with the maintainer before
opening a public issue.

## License

No license has been declared yet. Until one is added, the repository is not
automatically available for redistribution or reuse.
