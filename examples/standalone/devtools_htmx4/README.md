# DevTools htmx 2/4 lifecycle proof

This supporting example verifies Chirp's browser lifecycle integrations against
three pinned modes: htmx 2.0.10, htmx 4.0.0-beta5, and htmx 4 with the
`htmx-2-compat` extension.

The server uses typed `Template`, `Fragment`, `OOB`, and `Response` returns from
one template. The Playwright test checks that `window.ChirpHtmxDebug` records a
single request, history action, OOB update, and error per browser action; it
also checks islands mount/cleanup, safe-target processing, View Transitions,
and distinct general-error categories.

Run the server from this directory:

```bash
uv run python app.py
```

The browser modes are available at `/`, `/v4`, and `/v4-compat`. They load the
pinned htmx builds from jsDelivr, so the browser proof requires network access.

Run the browser proof after installing Playwright and Chromium:

```bash
uv sync --group dev --group browser
uv run playwright install chromium
uv run pytest test_browser_smoke.py
```
