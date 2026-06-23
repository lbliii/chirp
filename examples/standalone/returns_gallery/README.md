# Returns Gallery

Every Chirp response type on one page. **Read this first** if you're new to Chirp — it's the fastest way to learn the full surface.

```bash
PYTHONPATH=src python examples/standalone/returns_gallery/app.py
```

Then open http://127.0.0.1:8000/ and click through. Each card demonstrates one return type; each route in `app.py` has a docstring naming when to use it.

## What's here

| Route | Return type | When to use |
|-------|-------------|-------------|
| `GET /` | `Template` | Full-page render, no content negotiation |
| `GET /fragment` | `Fragment` | Named block, never a full page |
| `GET /page` | `Page` | Fragment for htmx, full page for browser |
| `POST /oob` | `OOB` | Multi-target swap (primary + out-of-band) |
| `GET /stream` | `Stream` | Flush sections as each resolves |
| `GET /suspense` | `Suspense` | Shell first, deferred blocks stream in |
| `GET /events` | `EventStream` | SSE channel for post-load updates |
| `POST /validate` | `ValidationError` | 422 + re-rendered form fragment |
| `POST /mutate` | `MutationResult` | One handler, three UX flows |
| `GET /redirect` | `Redirect` | Plain HTTP redirect |

## One template, many modes

`templates/gallery.html` is a single file with named blocks. The same template serves:

- the full index page (`Template`)
- standalone fragment renders (`Fragment`, `Page`)
- OOB swap targets (`OOB`)
- SSE event payloads (`EventStream`)
- form re-renders with errors (`ValidationError`)

No partials directory. No serialization layer. The block is the unit.

Swap-only payload blocks (`demo_form_ok`, `demo_sse_item`) use kida's `{% fragment %}` directive so they emit nothing during the full-page render — no `{% if defined %}` guards. Blocks that must paint on first load (for example `demo_mutation_counter`) stay as regular `{% block %}`.

## EventStream / SSE wiring

The EventStream card demonstrates current SSE vocabulary:

- Untargeted yielded `Fragment` values emit **unnamed** SSE frames. htmx listens on `sse-swap="message"` (the default channel).
- Put `sse-swap` on a **child sink**, not on the `sse-connect` element. The connect wrapper uses `hx-disinherit="hx-target hx-swap"` so the long-lived stream does not inherit broad layout targets.
- Named channels use `Fragment(..., target="name")` and matching `sse-swap="name"` listeners (see `reactive_tasks` for reactive block names).

Do **not** use the legacy `sse-swap="fragment"` attribute — Chirp 0.5+ defaults to the htmx `message` channel.

## Browser smoke

After pytest passes, confirm user-visible behavior:

1. Open `/` — every card renders; the EventStream log shows `Connecting…` then appended `[index] value=…` lines every ~0.8s.
2. Click **Load fragment** — only the fragment value updates in place (no full page).
3. Click **Trigger OOB swap** — both the primary region and `#oob-counter` update.
4. Submit the validation form with valid data — success message appears via the swap-only `demo_form_ok` fragment block.
5. Click **Increment counter** — `#mutation-counter` updates without a full reload.

Automated wiring proof: `uv run pytest examples/standalone/returns_gallery -q` (includes `assert_sse_wired` for `/` → `/events`).

## `Stream` and `Suspense` use side pages

`Stream` and `Suspense` each render a full HTML document of their own (the shell is theirs), so they use separate templates (`gallery_stream.html`, `gallery_suspense.html`) linked from the index.
