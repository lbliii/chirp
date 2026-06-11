# No-JS Floor — full CRUD with JavaScript disabled

The progressive-enhancement **floor**: a complete create / read / update /
delete app that keeps working when JavaScript never runs. Turn off htmx (CSP
block, NoScript, a flaky CDN, a crawler) and every mutation still succeeds.

This is the "diff-push killer": if a reviewer claims htmx is load-bearing for
correctness, this example is the counter-proof. The return-type-is-intent model
lets one handler serve both paths without branching on `HX-Request`.

## What it demonstrates

- **Plain `<form method="post">` for every mutation.** HTML forms can only issue
  GET and POST, so create / edit / delete are POST routes — htmx is *not*
  required to reach them. (htmx is layered on as `hx-post` for the enhanced
  path; the floor does not depend on it.)
- **POST/redirect/GET.** A plain (non-htmx) POST that succeeds returns
  `303 See Other` back to the list via `MutationResult`. Following the redirect
  shows the change, and a refresh does not re-submit the form.
- **Server-side validation that degrades gracefully.** An invalid submit returns
  `ValidationError` → `422` with the form block re-rendered inline, errors next
  to the fields, and the rejected values echoed back — no JS needed to see them.
- **One handler, two UX modes.** The same `MutationResult` returns rendered
  `Fragment` swaps for an htmx request and a `303` for a plain one. The intent
  lives in the return type, not in request sniffing.

## Run it

```bash
# From the repo root:
source .venv/bin/activate
PYTHONPATH=src python examples/standalone/nojs_floor/app.py
```

Then open <http://localhost:8000>. To experience the floor, disable JavaScript
in your browser (or delete the `<script src=".../htmx.org...">` line in
`templates/page.html`) and confirm create, edit, and delete still work — you'll
see full-page reloads via `303` instead of in-place htmx swaps.

## Test it

```bash
uv run pytest examples/standalone/nojs_floor/ -q
```

The tests in `test_app.py` drive the **no-JS path only** — they never send the
`HX-Request` header — and assert the `303` redirects, the followed-redirect
state changes, and the `422` re-rendered validation errors.

## Dependencies

Standalone — Chirp core only. No `chirp-ui`, no app shell, no optional extras.
