# Lucky Cat 🐱 — a Maneki-neko simulated trading-floor UI

> **Not your first Chirp app.** Complete the [learning path](../../../README.md#learning-path)
> first: [`standalone/hello`](../../standalone/hello/) →
> [`standalone/contacts`](../../standalone/contacts/) →
> [`chirpui/contacts_shell`](../contacts_shell/). Then use Lucky Cat as the
> capstone for signals, Suspense, SSE, and OOB together.

**▶ Live demo: <https://luckycat-production.up.railway.app>**

Browse markets, open a coin detail page with a live chart and order book, place
trades, and watch a Suspense portfolio dashboard stream in — all without a client
framework, a build step, or external services. Sign in with the demo account
(**`neko` / `luckycat`**) to trade; browsing is open to everyone.

> **Screenshot:** _No checked-in asset yet — open the live demo or run locally
> and capture the Markets Home lobby for docs._

The flagship **ChirpUI** example: a complete, multi-page trading floor built
entirely on Chirp — full pages, fragments, Server-Sent Events, server-owned
reactive signals, a Suspense dashboard, authentication, and the secure-by-default
stack. **No client-side framework — just htmx and server-owned state.** The
house token is **$MEOW**; market up is jade green, market down is lucky red.

It is a **simulated** trading floor, not a real exchange: prices come from an
in-process `SimFeed` (deterministic, same seed every run), orders fill against
in-memory stores, and there is no wallet-connect, no on-chain settlement, and no
matching engine. That keeps the example clone-and-run offline, CI-safe, and
focused on ChirpUI patterns rather than web3 plumbing.

## Feature map

Each feature, the Chirp **return type** it leans on, and the chirp-ui pieces it
composes.

| Feature | Route(s) | Return type | chirp-ui / composition |
|---------|----------|-------------|------------------------|
| **Markets Home (lobby)** | `GET /markets` + `GET /` alias | `Page` | curated lobby: stat strip, top-movers preview, watchlist preview + featured market, CTA into Research |
| **Trending** | `GET /markets/trending` (`?seg=…`) | `Page` / `Fragment` | segmented leaderboard; snapshot-per-swap, no live re-rank |
| **Research** | `GET /markets/research` (search/facet/sort/paginate) | `Page` / `Fragment` | power surface for 500+ coins; URL-param-driven `#research-results` swaps |
| **Market detail** | `GET /markets/{symbol}` | `Page` | server-rendered SVG chart + order book + trade tape |
| **— chart timeframe** | `GET /markets/{symbol}/chart?tf=` | `Fragment` | segmented 1m/1H/1D/1W toggle |
| **— live ticker/book/tape** | `GET /markets/{symbol}/stream` | `EventStream` | per-page SSE; OOB swaps for detail blocks |
| **Topbar live ticker** | `ticker` signal on `/_chirp/live` | live signal | rotating market spotlight on every page |
| **Topbar $MEOW balance** | `balance` signal on `/_chirp/live` | live signal | deposit + trade actions call `emit_signal('balance', …)` |
| **Trade (spot)** | `POST /trade` (`_action=order`) | `ValidationError` **or** `FormAction` | multi-target OOB: positions + open-order badge + toast |
| **— cancel** | `POST /portfolio/orders` (`_action=cancel`) | `FormAction` | per-row delete + count OOB |
| **— convert** | `POST /trade/convert` (`_action=convert`) | `Fragment` / `FormAction` | self-contained `#convert-form` swap |
| **Deposit** | `POST /markets` (`_action=deposit`) | empty 204 | modal via `data-action="deposit"`; emits balance + notifications signals |
| **Favorites** | `POST /watchlist/toggle`, `GET /markets/favorites` | `OOB` / `Page` | star toggle + starred-only grid |
| **Notifications bell** | `POST /notifications/read` + `notifications` signal | 204 / live signals | derived `notif_badge` / `notif_announce` on one connection |
| **Command palette (Cmd-K)** | `GET /search` | `Fragment` | chirp-ui `command_palette` dialog |
| **Suspense dashboard** | `GET /portfolio` | `Suspense` | shell-first; six panels stream in as OOB swaps |
| **Free-threading proof** | `GET /ft/stream` | `EventStream` | live ticks/sec panel on the portfolio page |
| **Sign in / out** | `GET`/`POST /login`, `POST /logout` | `Page` / `ValidationError` / `FormAction` | prefilled demo card; HX-Redirect reload on success |
| **Account gating** | gated `page.py` handlers | `@login_required` | anonymous → `/login?next=` |

Full route names, footguns, and composition notes live in [`DESIGN.md`](DESIGN.md)
§3.

## What this replaces

If you would reach for React/Next (or a separate SPA + API) for a trading-floor
product UI, Lucky Cat shows the Chirp alternative — grounded in what this
example actually does:

| Concern | Typical React / Next stack | Lucky Cat on Chirp |
|---------|---------------------------|-------------------|
| **Tooling** | `npm install`, bundler, build step, `node_modules` | No build step, no `node_modules` — Python + static CSS/JS only |
| **Live chrome** | Client state + WebSocket or client-managed SSE handlers | Server-owned `signal()` values on one `/_chirp/live` SSE connection |
| **Navigation** | Client router, hydration, layout re-fetch | Boosted htmx swaps `#main`; server re-renders the rail from the current path |
| **Forms & validation** | Client form lib + separate API routes | Return-type-as-intent in one handler: `ValidationError` (422) or `FormAction` |
| **Page-local live data** | WebSocket subscriptions + client reconciliation | `EventStream` pushes HTML fragments (detail chart/book/tape) — no client state graph |
| **Slow dashboard** | Loading spinners or client suspense boundaries | `Suspense`: shell paints with skeletons, panels stream as OOB swaps resolve |
| **Auth** | JWT in storage, client route guards | Session cookie, `@login_required`, `AuthMiddleware` in the secure stack |
| **Charts** | Chart.js / Recharts in the browser | Server-rendered SVG (`HeroChart`) — no JS chart library |
| **Deploy surface** | Node server (+ often a separate API tier) | Single Python process; demo pins `workers=1` for in-memory state |
| **Tests** | Jest/RTL + mocked fetch/WebSocket | `pytest` against deterministic `SimFeed` — offline, CI-safe, golden snapshots |
| **Real exchange / web3** | Wallet-connect, chain RPC, matching engine | **Out of scope** — simulated `SimFeed`, in-memory wallet, no chain |

## Start here — read in this order

New to Lucky Cat? Skim these files in order — each one introduces one layer of
the stack. Cross-check the primitive guides when a pattern is new:

| # | File | Why read it |
|---|------|-------------|
| 1 | [`pages/_layout.html`](pages/_layout.html) | The ChirpUI app shell: topbar, live signal sinks, two-tier rail, auth-aware chrome. |
| 2 | [`pages/page.py`](pages/page.py) | Filesystem routing entry — `GET /` aliases the Markets Home lobby (`Page` return type). |
| 3 | [`pages/login/page.py`](pages/login/page.py) | Auth showcase: `ValidationError` (422, form in place) vs `FormAction` (full reload on success). |
| 4 | [`pages/markets/_actions.py`](pages/markets/_actions.py) | First mutation: `POST /markets` with `_action=deposit` credits the wallet and `emit_signal('balance', …)` fans the topbar. See [Signals guide](../../../site/content/docs/build-apps/streaming-updates/signals.md). |
| 5 | [`pages/trade/page.py`](pages/trade/page.py) + [`pages/trade/_actions.py`](pages/trade/_actions.py) | Trade flow: `POST /trade` with `_action=order` → `ValidationError` or `FormAction` multi-target OOB. |
| 6 | [`pages/portfolio/page.py`](pages/portfolio/page.py) | **Advanced Suspense** — six deferred panels; learn the 4-line idiom in its module docstring first. See [Streaming HTML & Suspense](../../../site/content/docs/build-apps/streaming-updates/html-streaming.md). |
| 7 | [`app.py`](app.py) + [`wiring/`](wiring/) | Bootstrap only (~30 lines): middleware, signals, SSE routes. Mutations live under `pages/**/_actions.py`. |
| 8 | [`feed.py`](feed.py) | **DOMAIN** seam — `FeedSource` protocol + deterministic `SimFeed`. |

Deeper doctrine (IA rules, footguns, design tokens) lives in [`DESIGN.md`](DESIGN.md).

**Tutorial:** [Build a Live Trade Panel in 20 Minutes](../../../site/content/docs/tutorials/lucky-cat-trade-panel.md) —
a from-scratch build-along for the markets grid (`Page` at `GET /`) and the
`POST /trade` `_action=order` handler (`ValidationError` → `FormAction` multi-target OOB).

## What it demonstrates

**The app shell** — a full-viewport ChirpUI shell with a brand topbar, a live
cross-page ticker, a two-tier navigation rail (a persistent icon rail + an inner
rail whose sections change with where you are), and a mobile drawer. Boosted
navigation swaps only `#main` and the rail re-renders server-side from the current
path; `view_transitions="htmx"` animates the swaps.

**Markets & detail** (`Page`, `EventStream`) — a curated Markets Home lobby (stat
strip + top-movers / watchlist previews + a featured market + a Research CTA;
`/markets`, with `/` as an alias) plus Trending, Research, and Favorites as the
other fixed Markets destinations, and a per-market detail page with an interactive
gradient price chart (server-rendered SVG, no JS chart library), a depth-bar order
book, and a recent-trades tape. Each detail page opens its own `EventStream` that
pushes OOB fragment swaps as ticks arrive.

**Live cross-page chrome** (`signal()`) — the ticker, the $MEOW balance, and the
notifications bell are server-owned reactive **signals** fanned out over **one**
`/_chirp/live` SSE connection (declare-once / bind-many): a route calls
`app.emit('balance', …)` and every binding updates in lockstep — no hand-written
OOB twins. The bell folds a source signal plus two pure derived signals onto that
one connection.

**Trade flow** (`ValidationError`, `FormAction`) — the return-type-as-intent
showcase. An invalid order returns `ValidationError` → a **422** that re-renders
just the order form in place, with field errors and the submitted values
preserved; a clean fill returns a single `FormAction` whose multi-target OOB set
swaps the positions table, the open-order badge, and a toast (htmx gets fragments;
a plain POST gets a 303 redirect). The fill is free-threading-safe — the balance
re-check and wallet debit happen inside one lock, so two concurrent buys can never
both win.

**Portfolio dashboard** (`Suspense`) — the shell paints instantly with skeletons,
then six panels (value, P&L, holdings, allocation, open orders, activity) stream
in as their data resolves.

**Authentication** — public-browse, gated-trading, across all three gating levels
(see below).

**Honest free-threading** — the SimFeed fans every price tick across a
`ThreadPoolExecutor` (real CPU-bound parallelism, no `sleep()` fakery), and a live
ticks/sec figure on the portfolio page reads high on a `python3.14t`
(GIL-disabled) build and GIL-bound otherwise.

> The deep design doctrine — the information-architecture rules, the patterns
> worth stealing, the standing footguns, and the design tokens — lives in
> [`DESIGN.md`](DESIGN.md).

## Authentication

Lucky Cat is **public-browse, gated-trading**: anyone can browse the markets and a
coin's detail page, but the account section and every mutation require sign-in. It
shows the full range of gating, not a blanket lock:

- **Full-page gating** — `@login_required` on the account pages (`/trade`,
  `/portfolio`, `/activity`, `/markets/favorites`, `/settings`). An anonymous visit
  redirects to `/login?next=…`, and the prefilled sign-in card returns you there.
- **Component gating** — `current_user()` conditionals flip the chrome: the topbar
  shows "Sign in" or the user menu + Sign-out (and reveals the balance, bell, and
  Deposit action), and the watchlist star on the public markets grid becomes a
  "sign in to star" link.
- **Action gating** — `@login_required` on the mutation routes as the backstop.

The sign-in flow is return-type-driven: `ValidationError` re-renders the form in
place (422) on bad credentials, and a clean sign-in returns `FormAction` (an
HX-Redirect → full page reload, so the persistent topbar repaints its auth state).
`AuthMiddleware` joins the secure stack as `Session → Auth → CSRF →
SecurityHeaders`. The demo is a single shared in-memory account (**`neko` /
`luckycat`**, prefilled on the form), with passwords hashed by
`chirp.security.passwords` (stdlib scrypt fallback — no extra dependency).

## Run

```bash
pip install "bengal-chirp[ui]"
python examples/chirpui/lucky_cat/app.py
```

Open <http://127.0.0.1:8000/>. Browsing the markets needs no account; sign in
(demo creds **`neko` / `luckycat`**) to trade, deposit, and view your portfolio.
`/health` returns `200 ok` (the Railway healthcheck).

Working inside this repo instead of an install? Run against the editable checkout:

```bash
uv sync --group dev
PYTHONPATH=src uv run python examples/chirpui/lucky_cat/app.py
```

Run the test suite (deterministic + offline):

```bash
PYTHONPATH=src uv run pytest examples/chirpui/lucky_cat/
```

Opt-in browser smoke (Playwright — catches CSP-dead shells and runtime-only
failures that `TestClient` cannot see):

```bash
uv run --with playwright python -m playwright install chromium
uv run --with playwright pytest examples/chirpui/lucky_cat/test_browser_smoke.py -q
```

Link integrity (`test_links.py`) runs in the default suite via
``chirp.testing.assert_link_integrity`` — every rendered same-origin href must
resolve to 200.

## Realtime patterns

Return-type choice for streaming and live updates:
[realtime decision tree](https://lbliii.github.io/chirp/docs/build-apps/streaming-updates/realtime-decision-tree/)
(site) · feature map in [`DESIGN.md`](DESIGN.md) §4.

## Deploy (Railway)

The directory ships a `Dockerfile` and `railway.toml` so it runs as a standalone
Railway service. `app.run()` reads `PORT` and the `RAILWAY_*` hints through
`AppConfig.from_env()` and binds `0.0.0.0:$PORT` with no extra flags; the
healthcheck targets `/health`. Set `CHIRP_ENV=production`, `CHIRP_DEBUG=0`,
`CHIRP_LOG_FORMAT=json`, and a generated `CHIRP_SECRET_KEY` as service variables,
and keep it a **single web replica** (see [Production vs demo](#production-vs-demo) below). The full production
shape is in `docs/deployment/railway.md`.

## Production vs demo

Lucky Cat is a **single-process demo**, not a production multi-tenant deployment.
The table below is honest about what the example pins and what you must add for
real production.

| Concern | Demo (Lucky Cat) | Production |
|---------|------------------|------------|
| **Workers** | `workers=1` (in-memory state + one `/_chirp/live` pin) | `workers=N` + shared `SignalBackplane` |
| **State** | In-process wallet, trades, notifications, `SimFeed` | External store (DB/Redis) as source of truth |
| **Signals** | `InProcessBackplane` (default in `backplane.py`) | `RedisBackplane` or equivalent fan-out |
| **Secret** | Dev fallback when `env=development` | Required `CHIRP_SECRET_KEY` |

See [`DESIGN.md`](DESIGN.md) §7, [`backplane.py`](backplane.py), and the site
[production deployment guide](https://lbliii.github.io/chirp/docs/quality/deployment/production/)
for the full tier story. Do not claim this demo is production-ready multi-worker
without both a shared backplane and external state.

## Configuration

```python
config = replace(
    AppConfig.from_env(), template_dir=PAGES_DIR, worker_mode="async", workers=1
)
```

- `worker_mode="async"` powers the `EventStream` routes and the `/_chirp/live`
  signal stream.
- **`workers=1` is the single-process default.** The demo holds *all* state in
  process memory — the wallet, trade store, notifications, the SimFeed, the demo
  account, and the signal bus — and the single `/_chirp/live` connection is pinned
  to one worker. Scaling to `workers>1` is a **one-class swap**: implement the
  `SignalBackplane` protocol in `backplane.py` (the in-process default ships
  today; `RedisBackplane` is stubbed with wiring notes) **and** move stores into
  an external source-of-truth — the backplane carries fan-out, not ledger state.
  Each `@app.derived` signal must stay a *pure* function of its input signal
  values so deriveds stay correct once events cross process boundaries.
- `CHIRP_SECRET_KEY` signs sessions + CSRF. A dev fallback keeps local runs
  one-command; production (`CHIRP_ENV != development`) must set it.
- The market data source defaults to the deterministic `SimFeed`
  (`LUCKY_CAT_FEED=sim`) — no external dependencies, and it doubles as the test
  fixture. Live adapters are out of scope; only the `FeedSource` protocol seam and
  the sim ship.

## Structure

```
app.py            # App setup: secure stack (Session→Auth→CSRF→SecurityHeaders), /health,
                  #   mutation routes (deposit / trade / cancel / convert / watchlist / notifications-read),
                  #   live signals (balance / ticker / notifications + derived badge & announce),
                  #   per-market SSE stream, /logout, mount_pages
backplane.py      # SignalBackplane protocol + InProcessBackplane default + RedisBackplane stub
navigation.py     # Route-context nav model: RouteState (path-prefix *_active props) → shell_navigation()
wallet.py         # In-memory $MEOW wallet; backs /deposit + buys, fans out as the `balance` signal
trade_store.py    # Thread-safe trade backend: validate + atomic race-safe fills + resting limit orders
notifications.py  # Thread-safe bell log backing the `notifications` signal + its pure derived badge/announce
watchlist.py      # Thread-safe starred-markets set; backs the rail's Favorites lane + /markets/favorites
users.py          # Single shared in-memory demo account; backs AuthMiddleware + the login flow
shell.py          # Server-side rail-collapse cookie reader (no-flash first paint)
feed.py           # FeedSource protocol + deterministic SimFeed (worker-pool tick fan-out)
pages/
  _layout.html        # ChirpUI app shell: topbar, ticker, two-tier rail, auth-aware chrome
  _context.py         # markets, tickers, $MEOW token, shell actions, nav model
  page.py             # GET / — alias rendering the Markets Home lobby (markets/page.html)
  login/              # sign-in page (ValidationError 422 / FormAction redirect)
  markets/            # GET /markets — the curated Home lobby (page.py/.html) + the deposit modal
  markets/favorites/  # starred-only grid (the rail's Favorites destination; moved from /watchlist)
  markets/trending/   # gainers / losers / volume leaderboard (segmented #movers-region swaps)
  markets/research/   # the full-catalog power surface: search + facets + sort + paginate
  markets/{symbol}/   # market detail: chart + order book + trade tape (+ live SSE twins)
  trade/  + convert/  # place/cancel-order flow + $MEOW→market convert
  portfolio/          # Suspense dashboard (+ orders, history) + the free-threading panel
  activity/           # combined activity feed (+ deposits, trades)
  settings/           # account settings (+ security, display)
static/             # Maneki-neko palette + exchange chrome (lucky-cat.css) + rail/chart JS
```

## Build your own

Start a new ChirpUI project with the scaffold, then borrow patterns from this
example:

```bash
pip install "bengal-chirp[ui]"
chirp new myapp --shell
cd myapp
python app.py
```

The `--shell` scaffold wires `use_chirp_ui(app)`, boosted navigation, and the
secure-by-default middleware stack — the same foundation Lucky Cat builds on.
Clone this directory for the full trading-floor feature set, or read
[`DESIGN.md`](DESIGN.md) for the IA doctrine and patterns worth stealing.
