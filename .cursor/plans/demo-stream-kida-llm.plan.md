---
name: ""
overview: ""
todos: []
isProject: false
---

# Plan: Three Missing Demonstrations

Demonstrate the last three gaps from the template-engine research:

1. **Chirp Stream** — `return Stream(...)` with awaitables (progressive chunked HTML)
2. **Kida template streaming** — `{% async for %}` + `render_stream_async` (O(n) vs Fragment-per-token)
3. **LLM streaming with Kida** — Same as #2, applied to chat/RAG (the "wow" use case)

---

## Demo 1: Chirp Stream

**Goal**: Show `return Stream("page.html", stats=..., feed=...)` producing chunked HTML with faster TTFB.

**Current state**: Stream is implemented in `negotiation.py` and `templating/streaming.py` but no example uses it. The README feature table incorrectly lists `dashboard` as using Stream (it uses Template + EventStream).

**Approach**: Add a new example or extend an existing one.

### Option A: New `streaming/` example (recommended)

- **Location**: `examples/streaming/`
- **Concept**: "Progressive dashboard" — page shell streams immediately, then stats and feed blocks as their async data resolves.
- **Caveat**: Chirp's Stream resolves *all* awaitables before rendering, then streams the template. So the "progressive" part is chunked transfer (head → stats → feed), not "stats fills in when ready." For true shell-first-then-blocks, use Suspense (dashboard_live).
- **Actual behavior**: `Stream` with awaitables → resolve concurrently → `render_stream()` yields at statement boundaries. TTFB improves because we send chunks instead of buffering.
- **Template structure**:

```html
  <!DOCTYPE html>
  <html><head><title>Streaming Demo</title></head><body>
  <header>Progressive Load</header>
  <section id="stats">{% block stats %}...{% end %}</section>
  <section id="feed">{% block feed %}...{% end %}</section>
  </body></html>
  

```

- **Handler**:

```python
  async def load_stats():
      await asyncio.sleep(0.5)  # Simulate slow DB
      return [{"label": "A", "value": 1}, ...]

  async def load_feed():
      await asyncio.sleep(1.0)  # Simulate slower API
      return [{"title": "Item 1"}, ...]

  @app.route("/")
  async def index():
      return Stream("dashboard.html", stats=load_stats(), feed=load_feed())
  

```

- **Files**: `app.py`, `templates/dashboard.html`, `test_app.py`, `README.md`
- **Test**: Assert response is chunked, body contains expected HTML.

### Option B: Extend `dashboard/`

- Add a second route `/stream` that returns `Stream(...)` instead of `Template(...)`.
- Simpler but mixes concerns; Option A is cleaner.

**Recommendation**: Option A — new `streaming/` example.

---

## Demo 2: Kida Template Streaming (`{% async for %}`)

**Goal**: Show Kida's `render_stream_async` with `{% async for %}` — template consumes an async iterator and yields chunks as it iterates. O(n) work, not O(n²) re-render-per-token.

**Current state**: Kida has `examples/llm_streaming/` (standalone, no Chirp). Chirp does not expose a return type that uses Kida's `template.render_stream_async()`.

**Gap**: Chirp's `Stream` uses `render_stream()` (sync) after resolving awaitables. It never calls Kida's `render_stream_async()`, which is required for templates containing `{% async for %}` or `{{ await }}`.

**Approach**: Add Chirp support for "template with async iterator in context" → use Kida's `render_stream_async` → return `StreamingResponse`.

### Implementation options

**Option A: Extend `Stream` to detect async iterators**

- If context contains an `AsyncIterator` (or `AsyncGenerator`), use `template.render_stream_async(**context)` instead of resolve-then-render_stream.
- Challenge: Awaitables vs async iterators are different. Stream currently handles awaitables. An async iterator is not awaitable per se; it's used inside the template.
- Could add: `Stream("chat.html", stream=llm.stream(prompt))` — `stream` is an async iterator. Negotiation checks for async iterators in context; if present, uses `render_stream_async`.

**Option B: New return type `TemplateStream`**

- `TemplateStream("chat.html", stream=llm.stream(prompt), prompt=...)`
- Explicit, no overloaded semantics on Stream.
- Negotiation: if `TemplateStream`, get template, call `template.render_stream_async(**context)`, wrap in StreamingResponse.

**Option C: Helper that returns `StreamingResponse` directly**

- `from chirp import stream_template`
- `return stream_template("chat.html", stream=..., prompt=...)` → returns `StreamingResponse`.
- Handler returns a Response-like object; negotiation would need to pass it through.

**Recommendation**: Option B — `TemplateStream` keeps Stream's semantics clear (awaitables in context) and adds a dedicated type for async-iterator streaming.

### Chirp changes (for Option B)

1. `**chirp/templating/returns.py`**: Add `TemplateStream` dataclass.
2. `**chirp/server/negotiation.py`**: Add case for `TemplateStream` → get template, `render_stream_async`, `StreamingResponse`.
3. `**chirp/__init__.py**`: Export `TemplateStream`.

### Kida template (reuse pattern from Kida's llm_streaming)

```html
<div class="response">
  {% async for token in stream %}{{ token }}{% end %}
</div>
```

### Demo location

- **Chirp**: New example `examples/llm_streaming_kida/` — minimal chat UI, one route that returns `TemplateStream` with `stream=llm.stream(prompt)`.
- **Or** extend `ollama` or `llm_playground` with an alternative route `/chat/kida-stream` that uses `TemplateStream` for comparison.

---

## Demo 3: LLM Streaming with Kida (Unified)

**Goal**: Same as Demo 2, but framed as the "LLM streaming" showcase — the template-engine differentiator.

**Approach**: Demo 2 and 3 are the same implementation. Demo 3 is the *positioning* and *documentation*:

- README: "LLM streaming with Kida — O(n) template rendering, not Fragment-per-token."
- Compare: Fragment-per-token (current ollama/rag_demo) vs TemplateStream (new).
- Optional: Add a toggle or second route in `ollama` or `llm_playground` to switch between the two modes for side-by-side comparison.

**Deliverables**:

1. `TemplateStream` return type + negotiation (from Demo 2).
2. Example `examples/llm_streaming_kida/` or route in existing LLM example.
3. Docs: "Streaming LLM responses" — when to use Fragment-per-token (SSE, htmx) vs TemplateStream (chunked HTML, single request).

---

## Summary: Implementation Order


| #   | Task                                       | Location                                          | Depends    |
| --- | ------------------------------------------ | ------------------------------------------------- | ---------- |
| 1   | Chirp Stream example                       | `examples/streaming/`                             | None       |
| 2   | `TemplateStream` return type               | `chirp/templating/returns.py`, `negotiation.py`   | None       |
| 3   | LLM + TemplateStream example               | `examples/llm_streaming_kida/` or extend `ollama` | #2         |
| 4   | Update README feature table                | `examples/README.md`                              | #1         |
| 5   | Docs: Stream vs Suspense vs TemplateStream | `site/content/docs/`                              | #1, #2, #3 |


---

## Demo 1 Detail: `streaming/` Example

**Files to create**:

```
examples/streaming/
├── app.py
├── templates/
│   └── dashboard.html
├── test_app.py
└── README.md
```

**app.py** (~40 lines):

- `load_stats()` — async, 0.5s delay, returns list of dicts.
- `load_feed()` — async, 1.0s delay, returns list of dicts.
- `@app.route("/")` → `return Stream("dashboard.html", stats=load_stats(), feed=load_feed())`.
- Run: `python app.py`.

**dashboard.html**:

- Shell with header.
- `{% block stats %}` — loop over stats.
- `{% block feed %}` — loop over feed.
- Blocks use Kida's `{% block %}` so `render_stream` yields at boundaries.

**test_app.py**:

- `TestStreaming`: GET `/`, assert status 200, assert "stats" and "feed" in body.
- Optionally assert `Transfer-Encoding: chunked` if TestClient exposes headers.

---

## Demo 2/3 Detail: `TemplateStream` + LLM Example

**TemplateStream** (minimal):

```python
@dataclass(frozen=True, slots=True)
class TemplateStream:
    """Render a template with Kida's render_stream_async.

    Use when the template contains {% async for %} or {{ await }}
    and context includes async iterators or awaitables that the
    template consumes during rendering.

    Usage::
        return TemplateStream("chat.html",
            stream=llm.stream(prompt),
            prompt=prompt,
        )
    """
    template_name: str
    context: dict[str, Any] = field(default_factory=dict)
```

**Negotiation** (new case before EventStream):

```python
case TemplateStream():
    if kida_env is None:
        raise ConfigurationError(...)
    tmpl = kida_env.get_template(value.template_name)
    chunks = tmpl.render_stream_async(**value.context)
    return StreamingResponse(
        chunks=chunks,  # AsyncIterator
        content_type="text/html; charset=utf-8",
    )
```

**Note**: `StreamingResponse` must accept an async iterator for `chunks`. Verify `chirp.http.response.StreamingResponse` and `send_streaming_response` support `async for chunk in chunks`.

**Example `llm_streaming_kida/app.py`**:

- Requires `chirp[ai]` or Ollama.
- Route `POST /ask` or `GET /ask?prompt=...`: return `TemplateStream("response.html", stream=llm.stream(prompt), prompt=prompt)`.
- Template: `{% async for token in stream %}{{ token }}{% end %}`.
- Simple HTML page with form; response area uses `hx-get` with `hx-swap="innerHTML"` or a plain form POST that returns the streaming response. For chunked HTML swap, htmx supports `hx-swap="innerHTML"` on a streaming response — verify.

---

## Open Questions

1. **htmx + chunked HTML**: Does htmx's `hx-swap` work with a chunked `text/html` response, or does it require a complete body? (SSE is different — discrete events. Chunked HTML is one response that arrives in pieces.) If not, the TemplateStream demo may need a plain form POST with `fetch` + `ReadableStream` on the client, or a dedicated endpoint for non-htmx consumers.
2. **Kida block_metadata**: Suspense uses `template.block_metadata()` for `depends_on`. Does Kida's block_metadata work with `{% async for %}` blocks? (Likely yes — it's static analysis.)

**Verified**: `StreamingResponse.chunks` accepts `Iterator[str] | AsyncIterator[str]` and `send_streaming_response` handles both (sender.py:86-105).

---

## Success Criteria

- `examples/streaming/` runs and demonstrates Stream with async context.
- `TemplateStream` is implemented and exported.
- `examples/llm_streaming_kida/` (or equivalent) demonstrates LLM tokens streaming via Kida's `{% async for %}`.
- README feature table updated (Stream in streaming example).
- Docs explain Stream vs Suspense vs TemplateStream and when to use each.

