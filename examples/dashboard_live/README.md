# Dashboard Live

A real-time sales dashboard built on `chirp.data`. It demonstrates
`App(db=..., migrations=...)`, typed reads, live fragment updates over SSE, and
the kind of polling-or-push workflow you would use for production dashboards.

## Run

```bash
pip install chirp[data]
cd examples/dashboard_live && python app.py
```

## Test

```bash
pytest examples/dashboard_live/
```
