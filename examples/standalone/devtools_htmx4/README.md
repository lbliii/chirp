# DevTools htmx 2/4 lifecycle proof

This supporting example verifies Chirp's browser lifecycle integrations against
four pinned modes: htmx 2.0.10, native htmx 4.0.0-beta5, htmx 4 with the
`htmx-2-compat` extension, and Chirp's managed htmx 4 preview bundle.

The server uses typed `Template`, `Fragment`, `OOB`, and `Response` returns from
one template. The Playwright test checks that `window.ChirpHtmxDebug` records a
single request, history action, OOB update, and error per browser action; it
also checks islands mount/cleanup, safe-target processing, View Transitions,
and distinct general-error categories.

The managed preview app uses the exact public opt-in, injects core → compat →
SSE with one CSP nonce, and exposes configured/live compatibility metadata
through `window.ChirpHtmxDebug.getHtmxCompatibility()`.
Its second browser contract proves the frozen defaults: implicit compatibility
inheritance, local 422 swaps, broad 500 suppression, main-first OOB processing,
explicit DELETE query data, timeout cancellation, serialized `hx-sync`
requests, and server-authoritative history refetch.

Run the server from this directory:

```bash
uv run python app.py
```

The browser modes are available at `/`, `/v4`, and `/v4-compat`. They load the
pinned htmx builds from jsDelivr, so the browser proof requires network access.
The Playwright suite also starts `preview_app` on a separate port to keep its
single-version templates isolated from the manual multi-version fixture.

Run the browser proof after installing Playwright and Chromium:

```bash
uv sync --group dev --group browser
uv run playwright install chromium
uv run pytest test_browser_smoke.py
```
