# Streaming — Stream() and TemplateStream()

- **/** — `Stream()` with awaitables. Resolves concurrently, then chunks stream out.
- **/live** — `TemplateStream()` with slow async iterator. **Watch chunks arrive every 2 seconds.**

## Run

```bash
cd examples/streaming && python app.py
```

Open http://127.0.0.1:8000/live — items appear one by one every 2 seconds.

## What It Shows

- **Stream** — `Stream(template, **context)` where context can include awaitables
- **TemplateStream** — `TemplateStream(template, stream=async_iterator)` — template consumes with `{% async for %}`, chunks yield as it iterates
- **Visible chunk delivery** — /live demonstrates progressive rendering with 2s delays

## Stream vs Suspense vs TemplateStream

| | Stream | Suspense | TemplateStream |
|---|--------|----------|----------------|
| **When data resolves** | All awaitables before rendering | Shell first, blocks as they resolve | Template iterates as data arrives |
| **First paint** | After all data ready | Immediate (with skeletons) | Immediate, content streams in |
| **Use case** | Chunked TTFB, parallel fetches | Shell-first, progressive enhancement | LLM tokens, live feeds |
