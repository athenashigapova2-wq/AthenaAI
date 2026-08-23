# Pytest test layers

Install the development dependencies once:

```powershell
python -m pip install -r .\backend\requirements-dev.txt
```

Run every deterministic core check:

```powershell
python -m pytest
```

Run one layer:

```powershell
python -m pytest tests/unit
python -m pytest tests/integration
python -m pytest tests/evals
python -m pytest tests/simulation
```

The layers have distinct responsibilities:

- `unit`: isolated routing, resilience, nutrition, and client-lifecycle checks.
- `integration`: in-process FastAPI, Celery, agent graph, JMeter, and Grafana contracts.
- `evals`: deterministic offline datasets and quality gates.
- `simulation`: longitudinal scenarios using frozen application time and mock LLM.
- `live_evals`: external-provider checks excluded from the default suite.

See `tests/live_evals/README.md` for the deliberate three-step live opt-in.

