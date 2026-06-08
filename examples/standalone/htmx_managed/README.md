# Chirp-managed htmx — Mode A provisioning

This example writes `hx-*` attributes in its template and ships **no** htmx
`<script>` tag of its own. `AppConfig(htmx=True)` makes Chirp the single htmx
authority: the `HtmxInject` middleware appends the htmx runtime before `</body>`
on every full-page response, so the button actually fires.

This is **Mode A** of the `htmx_provisioning` contract. Because `htmx=True`
provisions htmx app-wide, `app.check()` passes even though the template uses
`hx-post`. Flip the flag off and the same template would raise an
`htmx_provisioning` ERROR — the attributes would be inert and the UI silently
dead, with no console error to point at the cause.

See `docs/build-apps/ui-extensions/htmx.md` for the full guide (CDN footgun,
`htmx_sse`, the `data-chirp="htmx"` dedup marker, and the contract).

## How It Works

- The page (`Template("counter.html")`) ships `hx-post="/increment"` on a button
  but no `<script src="...htmx...">`. Chirp injects htmx before `</body>` because
  `AppConfig(htmx=True)`.
- Clicking the button POSTs to `/increment`, which returns just the `counter`
  block as a `Fragment`. htmx swaps it into `#counter` via `hx-swap="outerHTML"`.

## Run

```bash
PYTHONPATH=src python examples/standalone/htmx_managed/app.py
```

Open the page and click Increment — the count updates with no full page reload.
View source on the served page and you will see the Chirp-injected
`<script src="https://unpkg.com/htmx.org@2.0.4" data-chirp="htmx"></script>`
that the template never declared.

## Test

```bash
pytest examples/standalone/htmx_managed/
```
