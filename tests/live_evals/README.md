# Live evaluations

This directory is intentionally outside the default `pytest` test paths. Tests
here may call GigaChat or another explicitly configured remote dependency.

Normal core checks never collect this directory:

```powershell
python -m pytest
```

Running live evaluations requires all three explicit actions:

1. Select `tests/live_evals` explicitly.
2. Pass `--run-live-evals`.
3. Set `ATHENA_RUN_LIVE_EVALS=1` in the same process.

TLS certificate verification is mandatory. By default the canonical Python
client uses `backend/certs/russian_trusted_root_ca_pem.crt`, the dedicated
Russian Trusted Root CA required by GigaChat. Override
`GIGACHAT_CA_BUNDLE_FILE` only when the environment supplies a reviewed PEM
bundle; missing or malformed bundles fail before any provider request.

```powershell
$env:ATHENA_RUN_LIVE_EVALS = "1"
python -m pytest tests/live_evals --run-live-evals
Remove-Item Env:ATHENA_RUN_LIVE_EVALS
```

Never enable the live environment variable in a shared or default CI job.

