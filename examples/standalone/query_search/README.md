# Complex QUERY Search

This is Chirp's canonical example for experimental HTTP `QUERY`: a structured,
read-only research search whose advanced facets are large enough to make a URI
awkward. It keeps the framework's hypermedia contract intact—one handler, one
Kida template, and one named `results` block serve full pages and htmx swaps.

## Run

```bash
PYTHONPATH=src python examples/standalone/query_search/app.py
```

No optional Python dependency is required. The GET floor is fully server
rendered and works without network access or JavaScript. The enhanced path
loads Chirp's pinned htmx client from its documented CDN, so that path needs
browser access to the CDN unless the application self-hosts htmx.

## What each path proves

| Path | Request | Result |
| --- | --- | --- |
| Native fallback | `GET /?q=python&topic=data` | Full page; compact URL remains bookmarkable and works with JavaScript disabled |
| Direct QUERY | `QUERY /` with URL-encoded content | Full page from `search.html` |
| Enhanced QUERY | `htmx.ajax("QUERY", ...)` | Only the named `results` block |
| Invalid facets | Valid form content with a bad year/range | Typed `ValidationError` fragment with `422` |
| Malformed content | Invalid URL-encoded percent escape | Actionable `400` |

The advanced controls intentionally have no HTML `name`. A native form submit
therefore sends only `q` and `topic`; the inline progressive enhancement adds
the larger topic set, year range, citation floor, required abstract terms, and
open-access flag to the QUERY body. Chirp does not claim a declarative
`hx-query` attribute.

GET remains the right default for ordinary search. Choose QUERY only for safe,
idempotent reads whose structured input would make the URI impractical. This
example does not persist an equivalent GET resource: the compact GET subset is
the bookmarkable resource, while advanced results are intentionally ephemeral.
Real applications that need durable advanced-result identity should create an
opaque application-owned GET URL without copying sensitive query content.

Chirp's configuration-managed response cache remains GET-only. This example
does not opt experimental QUERY responses into caching. Applications that do
so must use the body-aware `query_cache_key`, short TTLs, explicit invalidation,
and deployment-specific vary inputs described in `docs/http-query.md`.

## Verify

```bash
uv run pytest examples/standalone/query_search/test_app.py -q
uv run pytest examples/standalone/query_search/test_browser_smoke.py -q
```

The browser smoke is opt-in: it skips when Playwright/Chromium is unavailable.
It proves both a JavaScript-disabled native GET and a real htmx QUERY swap.
