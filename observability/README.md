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

The script uses JMeter in non-GUI mode, writes the JTL file to the Windows temp
directory and sends aggregated metrics to InfluxDB. Open Grafana and select the
last 30 minutes.
