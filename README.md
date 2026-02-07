# chirp

A Python web framework for the modern web platform.

```python
from chirp import App

app = App()

@app.route("/")
def index():
    return "Hello, World!"

app.run()
```

Chirp serves HTML beautifully — full pages, fragments, streams, and real-time events — all
through its built-in template engine, [kida](https://github.com/lbliii/kida).

**Status:** Pre-alpha (Phases 0-4 complete). See [ROADMAP.md](ROADMAP.md) for the full vision.

## Key Ideas

- **HTML over the wire.** Serve full pages, template fragments, streaming HTML, and
  Server-Sent Events. Built for htmx and the modern browser.
- **Kida built in.** Same author, no seam. Fragment rendering, streaming templates, and
  filter registration are first-class features, not afterthoughts.
- **Typed end-to-end.** Frozen config, frozen request, chainable response. Zero
  `type: ignore` comments. `ty` passes clean.
- **Free-threading native.** Designed for Python 3.14t from the first line. Immutable data
  structures, ContextVar isolation, `_Py_mod_gil = 0`.
- **Minimal dependencies.** `kida` + `anyio`. Everything else is optional.

## Requirements

- Python >= 3.14

## Part of the Bengal Ecosystem

```
chirp       Web framework     (serves HTML)
kida        Template engine   (renders HTML)
patitas     Markdown parser   (parses content)
rosettes    Syntax highlighter (highlights code)
bengal      Static site gen   (builds sites)
```

## License

MIT
