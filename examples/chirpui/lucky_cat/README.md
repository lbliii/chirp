# Lucky Cat 🐱 — a Maneki-neko crypto exchange

The flagship **ChirpUI** example: a complete, multi-page crypto-exchange trading
floor built entirely on Chirp — full pages, fragments, Server-Sent Events,
server-owned reactive signals, a Suspense dashboard, authentication, and the
secure-by-default stack. **No client-side framework — just htmx and server-owned
state.** The house token is **$MEOW**; market up is jade green, market down is
lucky red.

**▶ Live demo: <https://luckycat-production.up.railway.app>**

It's the best place to see how Chirp's *return-type-as-intent* model and ChirpUI's
app shell compose into a real product. The market data is a deterministic
in-process simulation (`SimFeed`) — same seed, same ticks — so the example clones,
runs offline, and is CI-safe with zero external services.

## What it demonstrates

**The app shell** — a full-viewport ChirpUI shell with a brand topbar, a live
cross-page ticker, a two-tier navigation rail (a persistent icon rail + an inner
rail whose sections change with where you are), and a mobile drawer. Boosted
navigation swaps only `#main` and the rail re-renders server-side from the current
path; `view_transitions="htmx"` animates the swaps.

**Markets & detail** (`Page`, `EventStream`) — a markets grid and a per-market
detail page with an interactive gradient price chart (server-rendered SVG, no JS
chart library), a depth-bar order book, and a recent-trades tape. Each detail page
opens its own `EventStream` that pushes OOB fragment swaps as ticks arrive.

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
  `/portfolio`, `/activity`, `/watchlist`, `/settings`). An anonymous visit
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

## Deploy (Railway)

The directory ships a `Dockerfile` and `railway.toml` so it runs as a standalone
Railway service. `app.run()` reads `PORT` and the `RAILWAY_*` hints through
`AppConfig.from_env()` and binds `0.0.0.0:$PORT` with no extra flags; the
healthcheck targets `/health`. Set `CHIRP_ENV=production`, `CHIRP_DEBUG=0`,
`CHIRP_LOG_FORMAT=json`, and a generated `CHIRP_SECRET_KEY` as service variables,
and keep it a **single web replica** (see Configuration). The full production
shape is in `docs/deployment/railway.md`.

## Configuration

```python
config = replace(
    AppConfig.from_env(), template_dir=PAGES_DIR, worker_mode="async", workers=1
)
```

- `worker_mode="async"` powers the `EventStream` routes and the `/_chirp/live`
  signal stream.
- **`workers=1` is deliberate.** The demo holds *all* state in process memory —
  the wallet, trade store, notifications, the SimFeed, the demo account, and the
  signal bus — and the single `/_chirp/live` connection is pinned to one worker. A
  single-user in-memory demo is inherently single-process; real multi-worker
  realtime needs a shared bus backplane (Redis/Postgres pub-sub) plus an external
  state store — the production scaling path, out of scope here. It's also why each
  `@app.derived` signal must be a *pure* function of its input signal values,
  never a process-local read.
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
navigation.py     # Route-context nav model: RouteState (path-prefix *_active props) → shell_navigation()
wallet.py         # In-memory $MEOW wallet; backs /deposit + buys, fans out as the `balance` signal
trade_store.py    # Thread-safe trade backend: validate + atomic race-safe fills + resting limit orders
notifications.py  # Thread-safe bell log backing the `notifications` signal + its pure derived badge/announce
watchlist.py      # Thread-safe starred-markets set; backs the rail's Watchlist lane + /watchlist
users.py          # Single shared in-memory demo account; backs AuthMiddleware + the login flow
shell.py          # Server-side rail-collapse cookie reader (no-flash first paint)
feed.py           # FeedSource protocol + deterministic SimFeed (worker-pool tick fan-out)
pages/
  _layout.html        # ChirpUI app shell: topbar, ticker, two-tier rail, auth-aware chrome
  _context.py         # markets, tickers, $MEOW token, shell actions, nav model
  page.py / page.html # markets-grid landing + the deposit modal
  login/              # sign-in page (ValidationError 422 / FormAction redirect)
  markets/{symbol}/   # market detail: chart + order book + trade tape (+ live SSE twins)
  trade/  + convert/  # place/cancel-order flow + $MEOW→market convert
  portfolio/          # Suspense dashboard (+ orders, history) + the free-threading panel
  activity/           # combined activity feed (+ deposits, trades)
  settings/           # account settings (+ security, display)
static/             # Maneki-neko palette + exchange chrome (lucky-cat.css) + rail/chart JS
```
```
