# Chat Room

A multi-user chat room demonstrating bidirectional communication via SSE + POST.
The idiomatic chirp alternative to WebSocket — no protocol upgrade, no special
infrastructure. Just plain HTTP.

## What it demonstrates

- **SSE + POST = bidirectional** — `POST /chat/send` submits messages, `GET /chat/events` streams them
- **Pub-sub broadcast** — `ChatBus` modeled on `ToolEventBus` (asyncio.Queue per subscriber, Lock for the set)
- **Fragment rendering** — Each message is a kida-rendered HTML fragment pushed to all subscribers via SSE
- **Session-based usernames** — `SessionMiddleware` + `get_session()` for login
- **Thread-safe history** — Bounded deque with Lock for recent message storage
- **Zero client-side JavaScript** — htmx + SSE extension handle everything

## Architecture

```
Browser A                         Chirp                         Browser B
   |                                |                              |
   |--- POST /chat/send ---------->|                              |
   |    (hx-post, returns 204)     |                              |
   |                               |--- ChatBus.emit() --------->|
   |<-- SSE Fragment --------------|                              |
   |                               |--- SSE Fragment ----------->|
   |                                                              |
   |   (htmx appends the rendered message to both browsers)       |
```

## Run

```bash
PYTHONPATH=src python examples/standalone/chat/app.py
```

Open http://127.0.0.1:8000 in two browser tabs. Pick different usernames.
Messages from either tab appear in both — in real-time.

## Worker mode

SSE connections are long-lived — the server holds the connection open and
streams events as they arrive. This requires `worker_mode="async"` so that
SSE streams and POST handlers run as concurrent tasks in the same event loop.

The default `worker_mode="auto"` selects sync workers on Python 3.14t
(free-threading), which block one worker thread per SSE connection and
isolate each request in a separate event loop. That breaks in-memory
pub-sub patterns like `ChatBus` (the `asyncio.Queue` subscriber in one
thread's event loop can't be woken by `put_nowait` from another).

```python
config = AppConfig(template_dir=TEMPLATES_DIR, workers=1, worker_mode="async")
```

## Why not WebSocket?

SSE handles server-to-client push. `hx-post` handles client-to-server commands.
Together they give you bidirectional communication over plain HTTP — no protocol
upgrade, no special proxy configuration, no reconnection logic to write. The
browser's built-in SSE reconnection handles dropped connections automatically.
