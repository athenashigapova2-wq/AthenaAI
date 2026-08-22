# Local load-test observability

This stack stores JMeter metrics in InfluxDB 2 and visualizes them in Grafana.

## Start

```powershell
docker compose up -d influxdb grafana
docker compose ps influxdb grafana
```

- Grafana: http://127.0.0.1:3000
- InfluxDB: http://127.0.0.1:8086

Local-only credentials are stored in the ignored `observability/.env` file. A
tracked template is available at `observability/.env.example`.

Grafana provisions the `Athena JMeter InfluxDB` datasource and the
`Athena / Athena — JMeter Load Tests` dashboard automatically. No external
Grafana plugin is required because the InfluxDB datasource is built in.

## Send the fixed 5 x 5 baseline to Grafana

Keep a fresh `LOAD_TEST_ACCESS_TOKEN` in the current PowerShell session, then
run:

```powershell
.\backend\load_tests\jmeter\run-smoke-with-grafana.ps1
```

The default profile is fixed at five users, a 30-second ramp-up and five
iterations per user (25 planned E2E scenarios). Therefore the command above is
equivalent to:

```powershell
.\backend\load_tests\jmeter\run-smoke-with-grafana.ps1 `
    -Users 5 `
    -RampSeconds 30 `
    -Loops 5 `
    -Scenario baseline-5x5
```

The script uses JMeter in non-GUI mode and assigns every invocation a unique run
ID such as `baseline-5x5-20260821-071418`. That ID is stored in the InfluxDB
`application` tag, so metrics from separate runs are not combined.

After the test, the script writes two files to the Windows temp directory:

- `athena-jmeter-smoke-<timestamp>.jtl`: raw JMeter samples;
- `athena-jmeter-smoke-<timestamp>.summary.json`: full-run p50/p95/p99,
  duration, throughput, error rate and sample counts.

The final terminal output includes a `Grafana (this run only)` URL. Open that
exact URL: it selects the unique application tag and an absolute time range
around the run. The `Load-test run` dashboard selector can be used to switch to
another run without mixing their metrics.

The Grafana latency and throughput charts contain five-second Backend Listener
aggregates. The JSON summary and JTL remain authoritative for full-run
percentiles and throughput. The throughput chart counts only completed parent
`agent_chat_e2e` scenarios; POST, polling GET and assertion samplers are not
added to that E2E rate.
