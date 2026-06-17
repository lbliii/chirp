---
title: Lucky Cat
description: Flagship ChirpUI simulated trading-floor demo on server-owned signals
draft: false
weight: 15
lang: en
type: doc
tags: [examples, chirp-ui, app-shell, signals, sse, suspense, oob, auth]
keywords: [lucky cat, trading floor, signals, app shell, suspense, oob, sse, chirp-ui, authentication, login_required, current_user]
category: examples
---

## What it is

Lucky Cat is the flagship showcase: **$MEOW**, a simulated Maneki-neko trading
floor built entirely on Chirp and [[docs/build-apps/ui-extensions/chirp-ui|ChirpUI]].
Full pages, HTML fragments, a streaming portfolio dashboard, and a live
cross-page ticker — with no client-side framework and no build step. Prices,
fills, and balances are simulated in memory, so you can clone it, run it offline,
and read the code.

Reach for it when you want to see how a real, multi-page product wires
[[docs/about/core-concepts/return-values|return types]], live server state, and
the secure-by-default stack together.

**Live demo:** [luckycat-production.up.railway.app](https://luckycat-production.up.railway.app)

**Location:** `examples/chirpui/lucky_cat/`

It ships:

- a full-viewport app shell — brand topbar, cross-page ticker strip, and a
  collapsible navigation rail
- a Markets Home lobby and a market-detail page (`/markets/{symbol}`) with a
  server-rendered SVG price chart, a depth-bar order book, and a recent-trades tape
- a place/cancel-order trade flow built on Chirp return types
- a [[docs/examples/suspense-dashboard|Suspense]] portfolio dashboard whose
  panels paint as skeletons and stream in as their data resolves
- a cross-page ticker, balance, and notification bell bound to server-owned
  [[docs/build-apps/streaming-updates/signals|signals]] over one SSE connection
- public-browse / gated-trading [[docs/quality/deployment/auth-hardening|authentication]]
  across three gating levels

## What this replaces

If you would reach for React/Next (or a separate SPA + API) for a trading-floor
product UI, Lucky Cat shows the Chirp alternative.

:::{list-table}
:header-rows: 1

* - Concern
  - Typical React / Next stack
  - Lucky Cat on Chirp
* - **Tooling**
  - `npm install`, bundler, build step, `node_modules`
  - No build step, no `node_modules` — Python + static CSS/JS only
* - **Live chrome**
  - Client state + WebSocket or client-managed SSE handlers
  - Server-owned `signal()` values on one `/_chirp/live` SSE connection
* - **Navigation**
  - Client router, hydration, layout re-fetch
  - Boosted htmx swaps `#main`; server re-renders the rail from the current path
* - **Forms & validation**
  - Client form lib + separate API routes
  - Return type as intent in one handler: `ValidationError` (422) or `FormAction`
* - **Page-local live data**
  - WebSocket subscriptions + client reconciliation
  - `EventStream` pushes HTML fragments — no client state graph
* - **Slow dashboard**
  - Loading spinners or client suspense boundaries
  - `Suspense`: shell paints with skeletons, panels stream as OOB swaps resolve
* - **Auth**
  - JWT in storage, client route guards
  - Session cookie, `@login_required`, `AuthMiddleware` in the secure stack
* - **Charts**
  - Chart.js / Recharts in the browser
  - Server-rendered SVG — no JS chart library
* - **Deploy surface**
  - Node server (+ often a separate API tier)
  - Single Python process; demo pins `workers=1` for in-memory state
* - **Tests**
  - Jest/RTL + mocked fetch/WebSocket
  - `pytest` against a deterministic `SimFeed` — offline, CI-safe
* - **Real exchange / web3**
  - Wallet-connect, chain RPC, matching engine
  - **Out of scope** — simulated prices, in-memory wallet, no chain
:::

## Try it

Run the example, test it, or scaffold the same foundation for a new app.

::::{code-tabs}
:sync: meow

```bash title="Run it"
pip install "bengal-chirp[ui]"
PYTHONPATH=src python examples/chirpui/lucky_cat/app.py
# open http://127.0.0.1:8000/  —  sign in with neko / luckycat to trade
```

```bash title="Test it"
pytest examples/chirpui/lucky_cat/
```

```bash title="Scaffold your own"
pip install "bengal-chirp[ui]"
chirp new myapp --shell
cd myapp && python app.py
```

::::

Browsing the markets needs no account. Sign in (demo creds: `neko` /
`luckycat`) to trade, deposit, and view your portfolio. `chirp new --shell`
wires `use_chirp_ui(app)`, boosted navigation, and the secure-by-default stack —
the same foundation Lucky Cat builds on.

## Authentication

Lucky Cat is **public-browse, gated-trading**: anyone can browse the markets grid
and a coin's detail page, but the account section and every mutation require
sign-in. It shows the full range of gating, not a blanket lock:

- **Full-page gating** — `@login_required` on the account handlers (`/trade`,
  `/portfolio`, `/activity`, `/markets/favorites`, `/settings`). An anonymous hit
  is a 302 to `/login?next=<path>`.
- **Component gating** — `current_user()` conditionals: the topbar swaps "Sign in"
  for the user menu, and the watchlist star on the public grid becomes a "sign in
  to star" link.
- **Action gating** — `@login_required` on the mutation routes as the backstop.

## How it's wired

:::{dropdown} Internals: return types, Suspense, signals, and the auth stack
The internals below are for readers who want the exact mechanics. The
[[docs/tutorials/lucky-cat-trade-panel|trade-panel tutorial]] walks the same code
paths from scratch.

**Trade flow.** A clean fill returns one `FormAction` whose multi-target OOB set
swaps positions, balance, the open-order badge, and a toast. An invalid order
returns `ValidationError` for a 422 re-render with field errors and submitted
values preserved.

**Suspense dashboard.** Six panels render as skeletons in the shell, then stream
in as OOB swaps when their awaitables resolve. Use `{% if x is deferred %}` for
the loading-vs-loaded test; pass `defer_blocks` / `defer_map` when static
analysis can't discover a panel through macro arguments. See
[[docs/examples/suspense-dashboard|Suspense Dashboard]].

**Live chrome.** The cross-page ticker, $MEOW balance, and notification bell bind
to server-owned `signal()`s over one `/_chirp/live` SSE connection
(declare-once / bind-many), with a pure `derived` signal for the bell's
unread-count pill. See [[docs/build-apps/streaming-updates/signals|Signals]].

**Login flow.** Bad credentials return `ValidationError` (a 422 in-place
re-render). A clean sign-in calls `login()` and returns `FormAction` with no
fragments — htmx gets an `HX-Redirect` (a full reload so the persistent topbar
repaints), a plain POST gets a 303.

**Stack ordering.** `AuthMiddleware` joins the secure-by-default stack as
`Session → Auth → CSRF → SecurityHeaders`. Passwords are hashed via
`chirp.security.passwords` — argon2id when `chirp[auth]` is installed, stdlib
scrypt as the always-available fallback. A single in-memory demo account keeps
the example single-process (matching `workers=1`).
:::

## Deploy it

The example ships a `Dockerfile` and `railway.toml` so it runs as a standalone
Railway service: `python app.py` binds `0.0.0.0:$PORT` through
`AppConfig.from_env()`, and the healthcheck targets `/health`.

:::{note}
Keep it a single web replica. The demo holds all state — wallet, trade store,
`SimFeed`, signal bus — in process memory, which is why it pins `workers=1`.
:::

See [[docs/quality/deployment/production|Production Deployment]] for the full
production shape.

## Source

- [`app.py`](https://github.com/lbliii/chirp/blob/main/examples/chirpui/lucky_cat/app.py)
- [`README.md`](https://github.com/lbliii/chirp/blob/main/examples/chirpui/lucky_cat/README.md) — feature map
- [`DESIGN.md`](https://github.com/lbliii/chirp/blob/main/examples/chirpui/lucky_cat/DESIGN.md) — IA doctrine

## Build along

**[[docs/tutorials/lucky-cat-trade-panel|Build a Live Trade Panel in 20 Minutes]]** — a
from-scratch walkthrough of the markets grid (`Page` at `GET /`) and the
`POST /trade/order` return-type pair (`ValidationError` 422 in place →
`FormAction` multi-target OOB). Grounded in this example's real code paths.

:::{related}
:::
