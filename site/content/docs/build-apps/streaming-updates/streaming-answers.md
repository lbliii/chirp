---
title: Streaming answers — transport × client
description: Safe recipes for TemplateStream and EventStream LLM answers in Chirp
draft: false
weight: 12
lang: en
type: doc
tags: [streaming, templatestream, eventstream, sse, htmx, llm]
keywords: [templatestream, eventstream, sse, htmx, token streaming, llm]
category: guide
---

## Pick transport, then client shape

Streaming confuses two independent choices:

1. **Transport** — chunked HTTP (`TemplateStream`) vs SSE (`EventStream`)
2. **Client** — full-page navigation vs htmx in-place swap

Only two pairings are safe for a single growing answer:

:::{list-table} Safe pairings
:header-rows: 1

* - Goal
  - Transport
  - Client wiring
* - Simplest path; user navigates to a streaming page
  - `TemplateStream`
  - Plain `<form method="post">` — **no** `hx-target`
* - Stay on the same page; tokens append in a div
  - `EventStream`
  - POST → `Fragment` scaffold → parametric `sse-connect`
:::

Chirp warns on the bad pairings at freeze:

- `template_stream_client_shape` — htmx swap into a `TemplateStream` route
- `sse_token_swap_mode` — many small SSE Fragments with replace swaps
- `sse_eager_connect` — static `sse-connect` on a GET page (INFO)

See [[docs/quality/contracts-debugging/categories|Contract categories]] and
[[docs/build-apps/streaming-updates/realtime-decision-tree|Realtime decision tree]].

## Recipe 1 — TemplateStream (full page)

**Reach for:** one request, one growing answer, no live shell.

```python
@app.route("/ask", methods=["POST"])
async def ask(request: Request) -> TemplateStream:
    form = await request.form()
    prompt = (form.get("prompt") or "").strip()
    return TemplateStream("response.html", prompt=prompt, stream=get_stream(prompt))
```

```html
<!-- index.html — no htmx on this form -->
<form action="/ask" method="post">
  <input name="prompt" placeholder="Ask something..." autocomplete="off">
  <button type="submit">Stream</button>
</form>
```

```html
<!-- response.html — full page with async loop -->
<div class="response">{% async for token in stream %}{{ token }}{% end %}</div>
```

Canonical example: [[docs/examples/llm-minimal|LLM Minimal]] (first form),
`examples/standalone/llm_streaming_kida/`.

## Recipe 2 — EventStream (in place)

**Reach for:** htmx shell, parametric prompt, token append in one region.

**Step A — form swaps in a panel (not the stream itself):**

```python
@app.route("/stream/start", methods=["POST"])
async def stream_start(request: Request) -> Fragment:
    form = await request.form()
    prompt = (form.get("prompt") or "").strip()
    url = f"/stream?prompt={quote(prompt)}"
    return Fragment("sse_panel.html", "sse_panel", prompt=prompt, stream_url=url)
```

```html
<form hx-post="/stream/start"
      hx-target="#sse-section"
      hx-swap="innerHTML"
      hx-on::after-request="if(event.detail.successful) this.reset()"
      method="post">
  <input name="prompt" placeholder="Ask..." autocomplete="off">
  <button type="submit">Stream</button>
</form>
<div id="sse-section"></div>
```

Use **placeholder**, not `value`, on the input — `this.reset()` restores the
initial value attribute, not empty.

**Step B — panel connects with a dynamic URL:**

```html
<!-- sse_panel.html -->
<div hx-ext="sse" sse-connect="{{ stream_url }}" sse-close="close"
     hx-disinherit="hx-target hx-swap" style="display: contents">
  <p class="prompt">Prompt: {{ prompt }}</p>
  <div class="response" sse-swap="message" hx-target="this" hx-swap="beforeend"></div>
</div>
```

Per-token Fragments **must** use `beforeend` (append). `innerHTML` replaces the
whole answer on every token — only the last word stays visible.

**Step C — stream route:**

```python
@app.route("/stream", referenced=True)
async def stream(request: Request) -> EventStream:
    prompt = (request.query.get("prompt") or "").strip()

    async def generate():
        async for token in get_stream(prompt):
            yield Fragment("response.html", "token", token=token)
        yield SSEEvent(event="close", data="done")

    return EventStream(generate())
```

Canonical example: [[docs/examples/llm-minimal|LLM Minimal]] (SSE form),
`chirpui/llm_playground/` for a shell variant.

## Recipe 3 — Scaffold a new project

```bash
chirp new mydemo --stream
cd mydemo && python app.py
```

Generates both recipes with simulated tokens — no API keys.

For a one-shot SSE hello (not token streaming), use `chirp new myapp --sse`
instead.

## Testing checklist (good-first issues)

- [ ] `app.check()` — zero ERRORs
- [ ] If the form uses `hx-*`, tests send `HX-Request`
- [ ] SSE token sinks use `hx-swap="beforeend"`
- [ ] `@pytest.mark.issue(N)` acceptance when closing an issue

See `examples/README.md` → “AI curious”.

:::{related}
- [[docs/build-apps/streaming-updates/server-sent-events|Server-Sent Events]]
- [[docs/build-apps/streaming-updates/html-streaming|Streaming HTML]]
- [[docs/quality/contracts-debugging/categories|Contract categories]]
:::
