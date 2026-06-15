# ChirpUI Examples

These examples cover the ChirpUI and app-shell lane: component-driven layouts, boosted navigation, shell updates, and richer interactions on top of core Chirp.

They are the reference point for:

- `use_chirp_ui(app)`
- `AppConfig(..., delegation=True)` where needed
- app shell layouts and shell actions
- boosted navigation and shell-aware fragment behavior

## Run From Repo Root

```bash
# From the repo root:
source .venv/bin/activate
PYTHONPATH=src python examples/chirpui/pages_shell/app.py
```

## Representative Examples

- `lucky_cat`: the flagship ChirpUI demo — a Maneki-neko **$MEOW** crypto
  exchange. A markets grid plus a market-detail page (interactive price chart,
  depth-bar order book, recent-trades tape), a place/cancel-order trade flow
  (`FormAction` multi-target OOB on a clean fill, `ValidationError` 422
  re-render on a bad order), a `Suspense` portfolio dashboard whose six panels
  paint as skeletons and stream in, a starred-markets watchlist, an activity
  feed, a Cmd/Ctrl-K command palette, and a notification bell — with the
  cross-page ticker, $MEOW balance, and bell all bound to server-owned
  `signal()`s over one `/_chirp/live` SSE connection.
- `contacts_shell`: ChirpUI shell companion to the standalone contacts CRUD example
- `forum_shell`: compact product-shaped shell fixture with mounted pages, form contracts, repeated fields, JSON data islands, and OOB shell updates
- `pages_shell`: mounted pages and shell actions
- `shell_oob`: app shell with AST-driven OOB updates
- `islands_shell`: islands inside a shell-aware layout
- `kanban_shell`: full app-shell workflow with auth and live updates
- `rag_demo`: richer AI/documentation experience using the newer UI layer

## Inventory

- `contacts_shell`
- `forum_shell`
- `islands_shell`
- `kanban_shell`
- `llm_playground`
- `lucky_cat`
- `pages_shell`
- `rag_demo`
- `shell_oob`
- `sortable_reorder`

## Validation Expectation

These examples should prove the newer shell/UI layer, but they should not redefine baseline standalone Chirp behavior. If a pattern works here and not in standalone, document it as a ChirpUI capability rather than a core Chirp assumption.
