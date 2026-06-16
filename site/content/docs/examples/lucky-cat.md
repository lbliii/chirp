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

## What It Teaches

Lucky Cat is the marquee ChirpUI example: a Maneki-neko **$MEOW** simulated
trading-floor UI built entirely on the app-shell lane. Use it to see how a real,
multi-page product wires return types, signals, and the secure-by-default stack
together — there is no client-side framework, only htmx and server-owned state.

**Live demo:** [luckycat-production.up.railway.app](https://luckycat-production.up.railway.app)

**Location:** `examples/chirpui/lucky_cat/`

Prices, fills, and balances are simulated (`SimFeed` + in-memory stores) — no
wallet-connect, no chain, no matching engine. The example is deliberately
offline-safe so you can clone, run, and test without external services.

It demonstrates:

- a full-viewport `chirpui-app-shell` with a brand topbar, a cross-page ticker
  strip, and a two-tier (icon + route-context) collapsible rail
- a **Markets Home lobby** and a **market-detail** page (`/markets/{symbol}`)
  with a server-rendered price chart, a depth-bar order book, and a recent-trades
  tape, each fed by a per-market `EventStream`
- a place/cancel-order **trade flow**: a clean fill returns one `FormAction`
  whose multi-target OOB set swaps positions, balance, the open-order badge, and
  a toast; an invalid order returns `ValidationError` for a **422** re-render
  with field errors and submitted values preserved
- a `Suspense` **portfolio dashboard** whose six panels paint as skeletons and
  stream in as their awaitables resolve (`{% if x is deferred %}`, `defer_blocks`,
  `defer_map`)
- a starred-markets **watchlist**, an **activity feed**, and a Cmd/Ctrl-K
  **command palette**
- the cross-page **ticker**, **$MEOW balance**, and **notification bell** all
  bound to server-owned `signal()`s over one `/_chirp/live` SSE connection
  (declare-once / bind-many, with pure `derived` signals for the bell's
  unread-count pill)
- **authentication** that exercises all three gating levels — `@login_required`
  full-page gating of the account section (anonymous → `/login?next=`),
  `current_user()` component gating of the topbar chrome + the watchlist star on
  the public grid, and action gating on the mutation routes — over `AuthMiddleware`
  with a `ValidationError` / `FormAction` login flow

## What This Replaces

If you would reach for React/Next (or a separate SPA + API) for a trading-floor
product UI, Lucky Cat shows the Chirp alternative:

| Concern | Typical React / Next stack | Lucky Cat on Chirp |
|---------|---------------------------|-------------------|
| **Tooling** | `npm install`, bundler, build step, `node_modules` | No build step, no `node_modules` — Python + static CSS/JS only |
| **Live chrome** | Client state + WebSocket or client-managed SSE handlers | Server-owned `signal()` values on one `/_chirp/live` SSE connection |
| **Navigation** | Client router, hydration, layout re-fetch | Boosted htmx swaps `#main`; server re-renders the rail from the current path |
| **Forms & validation** | Client form lib + separate API routes | Return-type-as-intent in one handler: `ValidationError` (422) or `FormAction` |
| **Page-local live data** | WebSocket subscriptions + client reconciliation | `EventStream` pushes HTML fragments — no client state graph |
| **Slow dashboard** | Loading spinners or client suspense boundaries | `Suspense`: shell paints with skeletons, panels stream as OOB swaps resolve |
| **Auth** | JWT in storage, client route guards | Session cookie, `@login_required`, `AuthMiddleware` in the secure stack |
| **Charts** | Chart.js / Recharts in the browser | Server-rendered SVG — no JS chart library |
| **Deploy surface** | Node server (+ often a separate API tier) | Single Python process; demo pins `workers=1` for in-memory state |
| **Tests** | Jest/RTL + mocked fetch/WebSocket | `pytest` against deterministic `SimFeed` — offline, CI-safe |
| **Real exchange / web3** | Wallet-connect, chain RPC, matching engine | **Out of scope** — simulated prices, in-memory wallet, no chain |

## Authentication

Lucky Cat is **public-browse, gated-trading**: anyone can browse the markets grid
and a coin's detail page, but the account section and every mutation require
sign-in. It shows the full range of gating, not a blanket lock:

- **Full-page gating** — `@login_required` on the account `page.py` handlers
  (`/trade`, `/portfolio`, `/activity`, `/markets/favorites`, `/settings`). An anonymous
  hit is a **302 to `/login?next=<path>`**; the prefilled card returns you there.
- **Component gating** — `current_user()` conditionals: the topbar swaps "Sign in"
  for the user menu (and reveals the balance, bell, and Deposit action), and the
  watchlist star on the public grid becomes a "sign in to star" link.
- **Action gating** — `@login_required` on the mutation routes as the backstop.

The login flow is return-type-driven: bad credentials → `ValidationError` (a
**422** in-place re-render), a clean sign-in → `login()` + `FormAction` (no
fragments → `HX-Redirect` for htmx, a full reload so the persistent topbar
repaints; a 303 for a plain POST). `AuthMiddleware` joins the secure stack
as `Session → Auth → CSRF → SecurityHeaders`, and a single in-memory demo account
keeps the example single-process (matching `workers=1`) with passwords hashed via
`chirp.security.passwords` (scrypt fallback — no extra dependency).

## Run It

```bash
pip install "bengal-chirp[ui]"
PYTHONPATH=src python examples/chirpui/lucky_cat/app.py
```

Open `http://127.0.0.1:8000/`. Browsing the markets needs no account; sign in
(demo creds: `neko` / `luckycat`) to trade, deposit, and view your portfolio.
`/health` returns `200 ok` (the Railway healthcheck).

## Test It

```bash
pytest examples/chirpui/lucky_cat/
```

## Deploy It

The example ships a `Dockerfile` and `railway.toml` so it can run as a
standalone Railway service: `python app.py` binds `0.0.0.0:$PORT` through
`AppConfig.from_env()`, and the healthcheck targets `/health`. Keep it a single
web replica — the demo holds all state (wallet, trade store, SimFeed, signal
bus) in process memory. See [[docs/quality/deployment/production|Production
Deployment]] for the full shape.

## Build Your Own

```bash
pip install "bengal-chirp[ui]"
chirp new myapp --shell
cd myapp
python app.py
```

The `--shell` scaffold wires `use_chirp_ui(app)`, boosted navigation, and the
secure-by-default stack — the same foundation Lucky Cat builds on. Clone the
example directory for the full trading-floor feature set, or read the
[`README.md`](https://github.com/lbliii/chirp/blob/main/examples/chirpui/lucky_cat/README.md)
and [`DESIGN.md`](https://github.com/lbliii/chirp/blob/main/examples/chirpui/lucky_cat/DESIGN.md)
for the feature map and IA doctrine.

## Source

- [`app.py`](https://github.com/lbliii/chirp/blob/main/examples/chirpui/lucky_cat/app.py)
- [`README.md`](https://github.com/lbliii/chirp/blob/main/examples/chirpui/lucky_cat/README.md)

## Build along

**[[docs/tutorials/lucky-cat-trade-panel|Build a Live Trade Panel in 20 Minutes]]** — a
from-scratch walkthrough of the markets grid (`Page` at `GET /`) and the
`POST /trade/order` return-type pair (`ValidationError` 422 in place →
`FormAction` multi-target OOB). Grounded in this example's real code paths.

## Next

- [[docs/build-apps/ui-extensions/app-shell|App Shells]]
- [[docs/build-apps/streaming-updates/sse-patterns|SSE patterns]]
- [[docs/examples/suspense-dashboard|Suspense Dashboard]]
- [[docs/examples/kanban-shell|Kanban Shell]]
