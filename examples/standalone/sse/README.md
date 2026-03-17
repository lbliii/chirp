# SSE

A minimal Server-Sent Events example. It shows how Chirp can stream plain
strings, structured `SSEEvent` payloads, and rendered HTML fragments to the
browser over a single long-lived HTTP response.

## Run

```bash
PYTHONPATH=src python examples/standalone/sse/app.py
```

## Test

```bash
pytest examples/standalone/sse/
```
