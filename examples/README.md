# Chirp Examples

Working examples that demonstrate chirp's core capabilities. Each is self-contained
and runnable — start the dev server or run the tests.

## Examples

### `hello/` — The Basics

Routes, return-value content negotiation, path parameters, Response chaining, error handlers.
No templates. Pure Python. Chirp in ~30 lines.

```bash
cd examples/hello && python app.py
```

### `todo/` — htmx Fragments

The killer feature. A todo list where the same template renders as a full page or a fragment,
depending on whether the request came from htmx. Add, toggle, and delete items with partial
page updates — zero client-side JavaScript.

```bash
cd examples/todo && python app.py
```

### `sse/` — Real-Time Events

Server-Sent Events pushing HTML fragments to the browser in real-time. The async generator
yields strings, structured SSEEvent objects, and kida-rendered Fragment objects — demonstrating
all three SSE payload types.

```bash
cd examples/sse && python app.py
```

### `dashboard/` — Full Stack Showcase

The complete Pounce + Chirp + Kida pipeline. A weather station with 6 live sensors:
streaming initial render, fragment caching, SSE-driven updates, and multi-worker
free-threading. Open your browser and watch the data change.

```bash
cd examples/dashboard && python app.py
```

## Running Tests

Each example has a `test_app.py` that verifies it works through the ASGI pipeline
using chirp's `TestClient`. No HTTP server required.

```bash
# All examples
pytest examples/

# One example
pytest examples/hello/
```

## What Each Example Exercises

| Feature | hello | todo | sse | dashboard |
|---|:---:|:---:|:---:|:---:|
| `@app.route()` | x | x | x | x |
| Path parameters | x | x | | |
| String returns | x | | | |
| Dict/JSON returns | x | | | |
| `Response` chaining | x | | | |
| `@app.error()` | x | | | |
| `Template` | | x | x | |
| `Fragment` | | x | x | x |
| `Stream` | | | | x |
| `request.is_fragment` | | x | | |
| `@app.template_filter()` | | x | | x |
| `EventStream` | | | x | x |
| `SSEEvent` | | | x | |
| `{% cache %}` | | | | x |
| `hx-swap-oob` | | | | x |
| Multi-worker Pounce | | | | x |
| `TestClient.fragment()` | | x | | |
| `TestClient.sse()` | | | x | x |
