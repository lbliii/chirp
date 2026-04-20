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

## `Stream` and `Suspense` use side pages

`Stream` and `Suspense` each render a full HTML document of their own (the shell is theirs), so they use separate templates (`gallery_stream.html`, `gallery_suspense.html`) linked from the index.
