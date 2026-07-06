# Chirp-managed htmx — Mode A provisioning

This example writes `hx-*` attributes in its template and ships **no** htmx
`<script>` tag of its own. `AppConfig(htmx=True)` makes Chirp the single htmx
authority: the inject middleware appends the htmx runtime before `</body>` on
every full-page response (with a per-request CSP nonce, dedup'd on
`data-chirp="htmx"`), so the button actually fires.

This is **Mode A** of the `htmx_provisioned` contract. Because `htmx=True`
provisions htmx app-wide, `app.check()` stays clean even though the template
uses `hx-post`. Flip the flag off and the same template trips the
`htmx_provisioned` **WARNING** — the attributes would be inert and the UI
silently dead, with no console error to point at the cause. The other
provisioning path is **Mode B**: ship your own htmx `<script>` in the layout
chain. Either one satisfies the contract.

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
`<script defer src="https://cdn.jsdelivr.net/npm/htmx.org@2.0.10/dist/htmx.min.js" data-chirp="htmx"></script>`
that the template never declared.

## Test

```bash
pytest examples/standalone/htmx_managed/
```
