# Historical failed run: 5 users x 5 iterations

Date: 2026-08-20
Scenario: `baseline-5x5`
Target: local Docker Compose stack with the real GigaChat provider

This report preserves the first unsuccessful real-provider 5 x 5 run. It is
historical evidence and is not the current baseline.

## Load profile

- Virtual users: 5
- Ramp-up: 30 seconds
- Iterations per user: 5
- Planned E2E scenarios: 25
- Celery worker concurrency: 4 threads

## Result

Source JTL: `athena-jmeter-smoke-20260820-075146.jtl`

| Metric | Result |
| --- | ---: |
| Planned E2E scenarios | 25 |
| Observed E2E scenarios | 24 |
| Successful | 23 |
| Failed | 1 |
| Missing after an aborted thread | 1 |
| Error rate among observed scenarios | 4.17% |
| Failed or missing versus planned scenarios | 8.00% |
| Test duration | 36.284 s |
| E2E throughput | 0.661 scenarios/s |
| Minimum E2E latency | 2.036 s |
| E2E latency p50 | 3.057 s |
| E2E latency p95 | 6.141 s |
| E2E latency p99 / maximum | 7.587 s |

## Failure analysis

- Failed job: `d5248eda-bd06-4da8-8923-d1dc9e6a11b5`
- Terminal status: `failed` after five polls
- Root cause: GigaChat returned HTTP 429 (`Too Many Requests`)
- The retry classifier treated the failure as transient and made three attempts
- FastAPI accepted the job with HTTP 202 and polling continued with HTTP 200
- The limiting component was the external provider quota, not the HTTP API

The 25th scenario did not run because the original JMeter Thread Group used
`Stop Thread` after a sampler error. The plan was subsequently changed to
`Start Next Thread Loop`, so a failed scenario no longer cancels the remaining
iterations assigned to that virtual user.

Grafana was also changed to count only failed parent `agent_chat_e2e`
transactions, preventing the parent transaction and terminal assertion from
representing the same logical failure twice.
