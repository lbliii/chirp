# SSE

A minimal Server-Sent Events example. It shows how Chirp can stream plain
strings, structured `SSEEvent` payloads, and rendered HTML fragments to the
browser over a single long-lived HTTP response.

## Run

```bash
cd examples/sse && python app.py
```

## Test

```bash
pytest examples/sse/
```
