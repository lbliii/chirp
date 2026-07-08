---
title: Full-Application Journey
description: A tested path from a SQLite page to a secure, live Chirp application
draft: false
weight: 35
lang: en
type: doc
tags: [tutorials, database, forms, htmx, sse, deployment]
keywords: [full stack python, sqlite, htmx, csrf, suspense, sse, app check]
category: tutorial
---

This journey answers a practical question: how do Chirp's individual
hypermedia primitives compose into a real application?

It uses five maintained examples instead of inventing another showcase. Each
stage isolates one new pressure; Lucky Cat is the integrated capstone. The
examples remain separate applications so you can read and test each concern
without carrying tutorial-only code into the next one.

## Fresh checkout

From a clean clone:

```bash
git clone https://github.com/lbliii/chirp.git
cd chirp
uv sync --group dev --extra auth --extra passkeys --extra sessions --extra ui
uv run python -m examples.inventory --check
```

The inventory check proves that every application below still exists, declares
its dependencies and capabilities, has the documented README status, and owns
an executable test entrypoint.

## Five-minute compiler proof

Run this focused slice before taking the longer journey:

```bash
uv run pytest \
  examples/standalone/todo/test_app.py::TestTodoOperations::test_plain_add_redirects_after_persisting \
  examples/standalone/todo/test_app.py::TestTodoOperations::test_empty_text_returns_422 \
  examples/chirpui/kanban_shell/test_app.py::TestBoard::test_index_boosted_fragment_keeps_page_content_contract \
  examples/chirpui/kanban_shell/test_app.py::TestSSE::test_sse_includes_oob_swaps \
  -q --tb=short

PYTHONPATH=src:. uv run chirp check examples.chirpui.kanban_shell.app:app

uv run pytest \
  tests/test_app/test_hypermedia_program.py::test_program_compiles_stable_route_template_block_target_graph \
  tests/test_transition_trace.py::test_same_route_has_distinct_normal_boosted_and_targeted_observations \
  -q --tb=short

PYTHONPATH=src:. uv run chirp freeze examples.standalone.freeze_site.app:app /tmp/chirp-frozen
```

That bounded loop proves each layer rather than asking you to trust a diagram:

- Todo executes SQLite-backed mutation and `ValidationError` paths through one
  template.
- Kanban exercises boosted outlet selection and post-load SSE/OOB updates.
- `chirp check` validates the assembled route/template/target contract.
- The compiler and transition tests show that the internal immutable program
  and runtime observations share stable transition identities.
- `chirp freeze` exports only the deliberately static-compatible example; the
  SQL, mutation, session, and SSE applications remain live ASGI programs.

For the visual half of the loop, start Lucky Cat with `CHIRP_DEBUG=1`, press
`Ctrl+Shift+D`, and compare its compiled transition IDs across normal,
boosted, targeted, mutation, Suspense, and SSE requests. The longer sections
below explain each piece and the three deliberate failure drills.

## The path

| Stage | Executable reference | New application pressure | Proof |
|---|---|---|---|
| 1 | [`standalone/todo`](https://github.com/lbliii/chirp/tree/main/examples/standalone/todo) | SQLite migrations and typed queries; one template negotiates full-page and named-block responses; CSRF, validation, htmx fragments, and a plain-POST redirect | `uv run pytest examples/standalone/todo -q` |
| 2 | [`chirpui/kanban_shell`](https://github.com/lbliii/chirp/tree/main/examples/chirpui/kanban_shell) | Filesystem pages, a persistent shell, boosted navigation, OOB mutations, auth, and SSE | `uv run pytest examples/chirpui/kanban_shell -q` |
| 3 | [`standalone/dashboard_live`](https://github.com/lbliii/chirp/tree/main/examples/standalone/dashboard_live) | SQLite-backed Suspense followed by post-load `EventStream` fragments | `uv run pytest examples/standalone/dashboard_live -q` |
| 4 | [`chirpui/lucky_cat`](https://github.com/lbliii/chirp/tree/main/examples/chirpui/lucky_cat) | Secure dual-mode mutations, shell OOB state, signals, targeted fragments, Suspense, SSE, DevTools, browser tests, and deploy posture | `uv run pytest examples/chirpui/lucky_cat -q` |
| 5 | [`standalone/freeze_site`](https://github.com/lbliii/chirp/tree/main/examples/standalone/freeze_site) | Optional static projection for routes whose output does not require live state | `uv run pytest examples/standalone/freeze_site -q` |

Run the focused journey suite at any point:

```bash
uv run pytest \
  examples/standalone/todo \
  examples/chirpui/kanban_shell \
  examples/standalone/dashboard_live \
  examples/chirpui/lucky_cat \
  examples/standalone/freeze_site \
  -q --tb=short
```

## 1. Persist one negotiated page

Start with `examples/standalone/todo/app.py` and its single `index.html`.
`Page("index.html", "todo_list", ...)` is the contract: a browser gets the
document and htmx gets the named list block. The same handler does not branch on
headers.

The mutation path adds the other half of progressive enhancement:

- `ValidationError` returns the list block with status 422 for inline htmx
  errors.
- `FormAction("/", Fragment(...))` returns the updated list to htmx and a 303
  redirect to a plain browser.
- `csrf_field()` and the standard form `method`/`action` keep the POST valid
  without relying on JavaScript-generated security state.

The tests exercise both request modes directly:

```bash
uv run pytest \
  examples/standalone/todo/test_app.py::TestTodoFullPage::test_index_full_page \
  examples/standalone/todo/test_app.py::TestTodoFullPage::test_index_fragment \
  examples/standalone/todo/test_app.py::TestTodoOperations::test_plain_add_redirects_after_persisting \
  -q
```

## 2. Add a shell without adding an API layer

Kanban Shell keeps server-rendered HTML as the transport. Read these paths in
order:

1. `pages/page.py` returns `Page` with both the narrow block and shell outlet.
2. `app.py` returns `ValidationError`, `Fragment`, and `OOB` from mutations.
3. `test_app.py` proves full, targeted, boosted, mutation, and SSE modes.

The boosted test is important: it verifies that `#main` receives an outlet
fragment, never a complete HTML document.

```bash
uv run pytest \
  examples/chirpui/kanban_shell/test_app.py::TestBoard::test_index_full_page \
  examples/chirpui/kanban_shell/test_app.py::TestBoard::test_index_fragment \
  examples/chirpui/kanban_shell/test_app.py::TestBoard::test_index_boosted_fragment_keeps_page_content_contract \
  examples/chirpui/kanban_shell/test_app.py::TestAddTask::test_add_returns_oob \
  -q
```

## 3. Separate first paint from post-load updates

Dashboard Live uses the same SQLite database for two different time horizons:

- `Suspense` renders the initial shell and streams resolved OOB blocks during
  the first response.
- `EventStream` sends new rendered fragments after the page has loaded.

That distinction is architectural, not stylistic. Use `Stream` for progressive
first-byte HTML, `Suspense` for shell plus deferred blocks, and `EventStream`
for post-load SSE.

## 4. Inspect the integrated application

Lucky Cat composes the preceding patterns and adds secure sessions, auth,
signals, browser evidence, and deployment files. Run it with debug tooling:

```bash
CHIRP_DEBUG=1 PYTHONPATH=src:. uv run python examples/chirpui/lucky_cat/app.py
```

Open the application, press `Ctrl+Shift+D`, and inspect
`window.ChirpHtmxDebug`. Compare a normal navigation, a boosted navigation, a
narrow market-chart swap, a trade mutation, the portfolio Suspense response,
and an SSE update. The response shape changes; the template/block contract does
not.

Then run static and behavioral evidence together:

```bash
PYTHONPATH=src:. uv run chirp check examples.chirpui.kanban_shell.app:app
uv run pytest examples/chirpui/lucky_cat/test_app.py -q
```

The browser smoke remains required for DOM behavior that static analysis cannot
prove. Install its opt-in dependencies before running it locally:

```bash
uv sync --group dev --group browser --extra auth --extra passkeys --extra sessions --extra ui
uv run playwright install chromium
uv run pytest examples/chirpui/lucky_cat/test_browser_smoke.py -q
```

## Runtime routes versus static projection

Static export is an optional projection, not Chirp's deployment model.

| Surface | Posture | Why |
|---|---|---|
| Todo `GET /` | Static-compatible only with an explicit, stable database snapshot | The HTML can render once, but its usefulness depends on later mutations. |
| Todo `/todos*` | Runtime-required | Writes, CSRF, validation, and redirects require the live app. |
| Dashboard `GET /` | Runtime-required | Initial HTML awaits live database queries through Suspense. |
| Dashboard `/events` | Runtime-required | It is a post-load SSE stream. |
| Kanban and Lucky Cat mutations, auth, signals, Suspense, and SSE | Runtime-required | They depend on request/session state or ongoing server work. |
| Freeze Site content routes | Static-compatible | Content is deterministic and the example declares freeze inputs explicitly. |

Use Freeze Site to learn the eligible path:

```bash
PYTHONPATH=src:. uv run chirp freeze examples.standalone.freeze_site.app:app /tmp/chirp-frozen
```

Do not freeze a mutation or SSE route and describe the output as equivalent to
the live application.

## Three bounded contract drills

These are temporary edits to maintained examples, not a second contract-lab
example. Restore the named file after each drill.

### Full document in a boosted target

In `examples/chirpui/kanban_shell/pages/page.py`, temporarily import `Template`
and replace the final `Page(...)` with
`Template("page.html", board=board, columns=columns, all_tasks=get_tasks(), active_filters=active_filters)`.
Then run:

```bash
uv run pytest \
  examples/chirpui/kanban_shell/test_app.py::TestBoard::test_index_boosted_fragment_keeps_page_content_contract \
  -q
```

The route-smoke failure names the boosted intent, `main` target, and observed
full-document shape. Restore `Page`: it carries the shell outlet and named block
negotiation that `Template` does not.

### Missing OOB block

In `_stats_fragment()` inside `examples/chirpui/kanban_shell/app.py`, change
`header_stats_oob` to `missing_stats_oob`, then run:

```bash
uv run pytest \
  examples/chirpui/kanban_shell/test_app.py::TestAddTask::test_add_returns_oob \
  -q
```

The request fails loudly instead of emitting an empty OOB wrapper. Restore the
declared block name (or add that named block to the same template); do not mark
the region optional to hide a typo.

### Mutating form without CSRF state

Remove `{{ csrf_field() }}` from
`examples/standalone/todo/templates/index.html`, then run:

```bash
PYTHONPATH=src:. uv run chirp check examples.standalone.todo.app:app
```

The `csrf_form` finding identifies `index.html` and tells you to restore
`csrf_field()`, add the configured hidden input, or explicitly exempt the route.
Restore the field; a meta tag used only by JavaScript is not a no-JavaScript
form fallback.

```bash
git restore examples/chirpui/kanban_shell/pages/page.py \
  examples/chirpui/kanban_shell/app.py \
  examples/standalone/todo/templates/index.html
```

## Downstream proof

The in-repository path is necessary but not sufficient. Furatena exercises the
same contracts through a substantially larger registry-driven application. The
pinned wheel-based compatibility canary in
[#556](https://github.com/lbliii/chirp/pull/556) checks out revision
`da584bf9fe19ec1376fdc0b23c7fb1b657b026b8`, installs the Furatena lockfile,
force-installs the built Chirp wheel, and runs the framework-facing integration
slice. Its advisory release result is the downstream evidence paired with this
journey; [#500](https://github.com/lbliii/chirp/issues/500) owns the canary's
release policy and update cadence.

:::{related}
:limit: 4
:section_title: Continue
:::
