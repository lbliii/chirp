# Dashboard Live

A real-time sales dashboard built on `chirp.data`. It demonstrates
`App(db=..., migrations=...)`, typed reads, live fragment updates over SSE, and
the kind of polling-or-push workflow you would use for production dashboards.

## Run

```bash
pip install chirp[data]
PYTHONPATH=src python examples/standalone/dashboard_live/app.py
```

## Test

```bash
pytest examples/standalone/dashboard_live/
```
