# Lucky Cat 🐱 — a Maneki-neko crypto exchange

A playful "lucky cat casino" trading-floor app shell built on ChirpUI: top-bar
brand + cross-page ticker strip, a markets sidebar, and a markets-grid landing.
House token is **$MEOW**; market up is jade green, market down is lucky red.

Live demo: <PLACEHOLDER — fill after deploy>

This example is built across several issues:

- **#221 (scaffold):** the ChirpUI app shell, Maneki-neko brand + palette, a
  Railway-ready `/health` route, and the secure-by-default stack
  (Session → CSRF → SecurityHeaders) so `app.check()` is ERROR-free.
- **#222:** a deterministic `SimFeed` behind a `FeedSource` protocol, wired into
  the markets grid and sidebar.
- **#223:** a market-detail page (`/markets/{symbol}`) with live price + 24h
  change, order-book depth, and a recent-trades tape, plus an `EventStream` route
  (`/markets/{symbol}/stream`) that pushes OOB fragment swaps as ticks arrive —
  including the cross-page ticker strip.
- **#230 (topbar):** a working **Deposit $MEOW** topbar action — `action="deposit"`
  renders a `data-action` button that opens a modal whose form POSTs to `/deposit`
  (CSRF-protected) and updates the balance over the live `balance` **signal**:
  `app.emit('balance', …)` fans one `event: balance` out to every
  `{{ signal('balance') }}` binding (the topbar token and the Trade buying-power
  line both swap together) over the single `/_chirp/live` connection — no
  hand-maintained OOB twin. The topbar uses multiple shell-action zones
  (primary / controls / overflow) so it reads like real exchange chrome.
- **#231 (progressive rail):** a two-tier **rail**. A persistent outer **icon rail**
  plus an inner **route-context rail** whose sections change with where you are
  (Markets / a market / Portfolio / Trade / Activity / Settings). The inner rail is
  driven by a server-side nav model (`navigation.py`: a frozen `RouteState` with
  path-prefix `*_active` properties → `shell_navigation()` returning typed
  `NavSection`/`NavItem`, empty sections pruned) and re-rendered through a single
  `sidebar_oob` region on boosted navigation. The inner rail is a **genuine
  continuous drag-resizer**: a rail-edge handle (`.luckycat-sidebar-resize`,
  `role="separator"`, `cursor: ew-resize`) you drag to set `--luckycat-rail-width`
  live, double-click to collapse/expand to the bare icon rail, and resize from the
  keyboard (arrow keys nudge, `Home`/`End` jump to min/max, `Enter`/`Space`
  collapse). Both preferences — the dragged width (`luckycat_rail_width`, a
  clamped/validated CSS-px integer) and the collapse boolean
  (`luckycat_rail_collapsed`) — persist to namespaced cookies and are read
  **server-side** (`shell.py`: `rail_width()` / `rail_is_collapsed()`) so the very
  first paint already reflects the persisted size + state (no flash, no
  flash-of-unsized-rail). The full-viewport shell pins the rails to `100dvh` with
  a sticky topbar and internal nav scroll; `view_transitions="htmx"` animates the
  boosted `#main` swaps.
- **Mobile chrome (`<48rem`):** below the shell's `48rem` breakpoint the inline
  two-tier rail and the topbar shell-actions (Deposit $MEOW + the "More"
  dropdown) are hidden, and a **hamburger** opens a chirp-ui **drawer**
  (`#lucky-cat-nav`, native `<dialog closedby="any">` + `chirpuiDialogTarget`)
  whose body reuses the SAME `shell_navigation` model as the rail (the rooms +
  the route-context sections, with the boosted shell-outlet contract and
  close-on-tap), so the two never drift. The market-detail order book + trade
  tape stack to a single column. It is **all** in `static/lucky-cat.css` media
  queries — the full-viewport desktop shell is unchanged.

### M2 — trade flow, Suspense dashboard, free-threading proof

- **#225 (trade flow):** `GET /trade` renders a place-order form alongside the
  live positions table and open-order count. `POST /trade/order` is the
  return-type-as-intent showcase: an invalid order returns
  `ValidationError("trade/page.html", "order_form", …)` → **422** with field
  errors and the submitted values preserved (the `order_form` block only, no
  full-page nav); a clean **market** order fills and returns a single
  **`FormAction`** whose multi-target OOB set swaps the positions table, the
  topbar `$MEOW` balance, the open-order count badge, and a toast (htmx gets the
  fragments; a plain POST gets a 303 redirect back to `/trade`). A **limit**
  order *rests* (the M2 sim has no matching engine) — it books an open order and
  bumps the live `#open-order-count`. The fill path is **free-threading-safe**:
  `trade_store.try_place_order` re-checks the balance and debits the wallet
  inside a single lock, so two concurrent buys racing the same balance can never
  both win — the loser gets a clean 422, never an unhandled-`ValueError` 500.
  `POST /trade/order/{id}/cancel` cancels a resting order and OOB-swaps the
  count + a toast.
- **#224 (Suspense portfolio dashboard):** `GET /portfolio` is the example's
  **`Suspense`** surface — the shell paints instantly with skeletons in every
  panel, then six deferred panels (value, P&L, holdings, allocation, open
  orders, activity) stream in as OOB swaps as their awaitables resolve from the
  thread-safe `trade_store`. Each loading branch tests **`{% if x is deferred %}`**
  (NOT `is not none`): a deferred value is the `DEFERRED` sentinel, so `is not
  none` would take the *loaded* branch against the sentinel and an *empty
  resolved* tuple would stick on a skeleton. `defer_blocks` bypasses static
  discovery (several deferred keys appear only inside chirp-ui macro args) and
  `defer_map` remaps every block whose section id ≠ block name (e.g.
  `portfolio_value` → `portfolio-value`) so each OOB swap lands on a real DOM id
  (fail-loud). Each panel's `<section>` carries its `id` only on the skeleton
  paint; the loaded re-render drops it so the OOB wrapper owns the id (no
  duplicate id after the outerHTML swap).
- **#227 Part A (free-threading proof):** the portfolio dashboard ships a
  visible FT panel with the honest GIL state and the worker-pool width (sync, in
  the shell), and `GET /ft/stream` is a small `EventStream` that OOB-swaps a live
  ticks/sec figure into `#ft-panel` as the SimFeed fans every tick across its
  worker pool — genuine CPU-bound parallelism, no sleeps.

## Run

Requires the ChirpUI extra (`pip install chirp[ui]`). Run from the repo root so
the bundled ChirpUI templates/static resolve. Use `uv run` so the pinned
`kida-templates` is used (a bare interpreter may have a stale kida that can't
`import chirp`):

```bash
PYTHONPATH=src uv run python examples/chirpui/lucky_cat/app.py
```

Then open <http://127.0.0.1:8000/>. `/health` returns `200 ok` (the Railway
healthcheck — see `docs/deployment/railway.md`).

> Never run the blocking server in tests. Sanity-check by importing the module
> and calling `app.check()` / `app.freeze()`, or run the scoped test suite:
>
> ```bash
> PYTHONPATH=src uv run pytest examples/chirpui/lucky_cat/test_app.py
> ```

## Deploy (Railway)

This directory ships the minimal deploy artifacts so it can run as a standalone
Railway service:

- `Dockerfile` — Python 3.14 + `uv pip install "bengal-chirp[ui]"`, then
  `python app.py`. The image is self-contained (it pulls Chirp from PyPI, not
  the repo checkout), so the build context is *this* directory, not the repo
  root.
- `railway.toml` — Dockerfile builder, `startCommand = "python app.py"`,
  `healthcheckPath = "/health"`, and a single web replica (the demo holds all
  state in process memory — see "Configuration" below).

`app.run()` reads `PORT` and the `RAILWAY_*` hints through
`AppConfig.from_env()`, so it binds `0.0.0.0:$PORT` on Railway with no extra
flags. Set `CHIRP_ENV=production`, `CHIRP_DEBUG=0`, `CHIRP_LOG_FORMAT=json`, and
a generated `CHIRP_SECRET_KEY` as service variables. See
`docs/deployment/railway.md` for the full production shape.

## Configuration

The app config is built from the environment so it is Railway-friendly:

```python
config = replace(
    AppConfig.from_env(), template_dir=PAGES_DIR, worker_mode="async", workers=1
)
```

- `AppConfig.from_env()` reads `CHIRP_*` env vars (and Railway's `PORT`). It does
  **not** accept `template_dir` / `worker_mode` / `workers`, so those are layered
  on with `dataclasses.replace`.
- `worker_mode="async"` is required for the live `EventStream` routes (#223) and
  the `/_chirp/live` signal stream.
- **`workers=1` is required** (not the CPU-count default). This example keeps ALL
  its state in process memory — the wallet, trade store, notifications log, the
  SimFeed, AND the signal bus behind `@app.signal`. Multiple OS-process workers
  would each hold a SEPARATE copy, so state would split across requests (a deposit
  on one worker invisible to the next) AND the `/_chirp/live` SSE connection —
  pinned to one worker — would stall page loads that land on a tied-up worker (the
  "white screen" freeze). A single-user in-memory demo is inherently
  single-process; real multi-worker realtime needs a shared bus backplane
  (Redis/Postgres pub-sub) + an external state store (the production scaling path,
  out of scope here). This is also WHY a `derived` must be a pure function of its
  input signal values — see "Live updates".
- `CHIRP_SECRET_KEY` is read for session/CSRF signing. The example falls back to
  a dev-only key in development; production deploys (`CHIRP_ENV != development`)
  must set `CHIRP_SECRET_KEY`.

## Feed selection

The market data source is chosen by the `LUCKY_CAT_FEED` env var (default
`sim`). The deterministic `SimFeed` (#222) has no external dependencies; an
unknown or unreachable source falls back to `sim` with a `logging.warning`. Live
adapters are out of scope for M1 — only the protocol seam and the sim default
ship.

## Live updates — signals + per-market SSE

**Cross-page chrome rides live `signal`s on ONE `/_chirp/live` connection.** A
signal is a server-owned reactive value pushed over a single merged SSE stream
(declare-once / bind-many): `{{ signal_connect() }}` in the shell opens that one
connection, and every binding swaps from the named events fanned out on it — no
hand-maintained OOB twins. Three signals power the chrome:

- **`balance`** — a PUSH signal (no source generator). `/deposit` and `/trade`
  call `app.emit('balance', new_balance)`, and every `{{ signal('balance') }}`
  binding swaps in lockstep: the topbar token AND the Trade page "buying power"
  line update together (the declare-once/bind-many showcase).
- **`ticker`** — a SOURCE-driven signal: a rotating market-spotlight async
  generator (`signal_block('ticker')` inside `#lucky-cat-ticker`) is the **sole**
  owner of the strip on every page, so two sources can never fight + flicker.
- **`notifications`** — the headline N→1 fold. The old separate
  `/notifications/stream` scope is gone; its drain + price-move-alert loop is now
  this SOURCE signal, which emits a `notifications.NotifFeed` snapshot (the recent
  rows AND the watermark-aware unread count, captured atomically) whenever the log
  changes. Two **DERIVED** signals recompute in the same emit cascade:
  - **`notif_badge`** (`@app.derived('notif_badge', on=('notifications',))`) — the
    unread-count pill, computed **purely** from `feed.unread`.
  - **`notif_announce`** — the visually-hidden spoken count, also from `feed.unread`.

  The pure-derived contract: a derived reads only its **input signal values**,
  never a process-local store — so the count travels inside the signal value
  rather than being re-read from the notifications store (deterministic across
  workers, race-free across threads). The bell's sinks are EXISTING elements
  (`#notif-list`, `#notif-badge`, `#notif-announce`) carrying manual `sse-swap`
  attributes — not `signal_block()` (which would inject its own wrapper).
  `app.check()`'s `signal_dead_binding` rule validates each of those `sse-swap`
  names against the registered producers.

**The market-detail page keeps its own per-market `EventStream`.** `/markets/{symbol}`
renders three live regions — ticker, order book, trade tape — with stable DOM ids
(`market-ticker`, `order-book`, `trade-tape`). `{{ sse_scope(...) }}` opens a
SECOND, page-specific SSE channel to `/markets/{symbol}/stream`; that route
iterates `get_feed().subscribe(symbol)` and per tick yields OOB fragment twins
`market_ticker_oob` / `order_book_oob` / `trade_tape_oob` (each shares one
inner-body macro with its full-page block and bakes `hx-swap-oob="innerHTML"`
against its DOM id, so they are yielded as bare `Fragment`s). This stream does
**not** drive the topbar strip — that has one global owner, the `ticker` signal.

The only remaining registered OOB region is `watchlist_count_oob` (the rail
count badge); the detail-page `*_oob` blocks bake their own wrappers (the kanban
idiom) and need no registration, and the ticker/balance/bell chrome moved off
OOB onto signals entirely.

## Structure

```
app.py                              # App (workers=1) + secure stack + chirp-ui-compatible CSP + /health + POST routes (/deposit, /trade/order, /trade/order/{id}/cancel, /trade/convert, /notifications/read) + live SIGNALS (balance/ticker/notifications + notif_badge/notif_announce derived) + per-market SSE stream + watchlist_count_oob region + mount_pages
navigation.py                       # Route-context nav model: RouteState (*_active props) + shell_navigation() → NavSection/NavItem
wallet.py                           # In-memory house $MEOW wallet (debit/deposit; reset() for test isolation); backs /deposit + buys, fans out as the `balance` signal
trade_store.py                      # Thread-safe trade backend: validate_order + atomic try_place_order (race-safe fills) + resting limit orders + positions/history reads
notifications.py                    # Thread-safe bell log: NotifFeed snapshot (rows + atomic unread count) backing the `notifications` signal + its pure derived badge/announce
watchlist.py                        # Thread-safe starred-markets set (toggle/count under one lock); backs the rail's Watchlist lane + /watchlist
shell.py                            # Server-side rail width + collapse cookie readers (template globals; drive no-flash first paint, clamp the width cookie)
feed.py                             # FeedSource protocol + deterministic SimFeed (warm-on-build; worker-pool tick fan-out for the FT proof)
pages/
  _layout.html                      # ChirpUI app shell: brand, ticker strip, two-tier rail (icon rail + inner sidebar_oob), balance
  _components/sidebar.html          # rail macros: icon-rail link, inner contextual rail, badges
  _context.py                       # markets, tickers, $MEOW token, shell actions (deposit/settings/overflow), nav model
  _meta.py                          # route title / breadcrumb
  page.py / page.html               # markets-grid landing + the deposit modal & data-action click handler
  markets/{symbol}/                 # market detail: price hero + interactive gradient area chart (1m/1H/1D/1W timeframe toggle hx-swaps #market-chart; hover crosshair reads a nonced JSON island) + depth-bar order book + trade tape (full-page blocks + *_oob twins)
  trade/                            # #225 place/cancel-order flow: order_form (422 re-render) + positions/count OOB twins
    convert/                        #   Trade → Convert: self-contained htmx form (hx-select="#convert-form" overrides the boosted shell so the 422 swaps in place, not the spot form)
  portfolio/                        # #224 Suspense dashboard (6 deferred panels, is-deferred skeleton-vs-loaded) + #227 FT proof panel + /ft/stream twin
    orders/  history/               #   Open orders + fill history (the inner-rail Portfolio lanes)
  activity/                         # all activity
    deposits/  trades/              #   the inner-rail Activity lanes
  settings/                         # profile settings
    security/  display/             #   the inner-rail Settings lanes
  # every inner-rail link resolves to a real page (link-integrity crawl in test_links.py asserts 200)
static/lucky-cat.css                # Maneki-neko palette + exchange chrome
static/lucky-cat-shell.js           # genuine continuous drag-resizer: pointer-drag width + double-click collapse + keyboard; writes the namespaced width/collapse cookies
```
