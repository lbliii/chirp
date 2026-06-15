# RFC: Lucky Cat — Markets section IA build-out

**Status**: Drafted (not started)
**Created**: 2026-06-15
**Owner decision needed**: see "Open decisions" — all have recommendations
**Epic**: #220 (Lucky Cat)
**Source**: live-demo review — the per-market inner rail is dead anchors that don't
scale to 500 coins; the free-threading panel shows GIL enabled; rail hover labels
are clipped; rail icons are generic.

---

## Why

The Markets room's contextual rail currently renders **one row per market** (no
cap — `navigation.py` `_markets_sections`), and on a coin detail route adds an
Overview/Order-book/Trades/Info section whose three anchors jump to sections
already in view. It's low-value and O(N): at 500 coins the rail emits 500 rows.

## Locked IA

The Markets room's contextual rail becomes **fixed destinations** ("where you are
within Markets"), + the current coin pinned only on a detail route:

| View | Route | Today | What it is |
|------|-------|-------|------------|
| **Home** | `/markets` (+ `/` alias) | `/` grid (`pages/page.py`) | Curated lobby: stat strip, top-movers preview, watchlist preview, featured, CTA into Research. **Bounded** (~9 cards). |
| **Favorites** | `/markets/favorites` | `/watchlist` | Starred coins (relabel + move). |
| **Trending** | `/markets/trending` | — (new) | Gainers / losers / volume, top-N (segmented htmx swaps). |
| **Research** | `/markets/research` | — (new) | The power surface: search + facet filters (price/change/volume/sector) + sortable columns + **server-side pagination** + lightweight compare. The scalable home for 500+ coins. |
| **Coin** | `/markets/{symbol}` | exists | Detail; pinned in the rail when active. |

The full catalog lives **only** in Research (filtered/sorted/sliced server-side),
never the rail. **Cmd-K = the lightweight quick-jump; Research = the full surface**
— they share one substring matcher so they never drift.

## PR sequence

**Ship-now (IA-independent — land first, reviewable in isolation):**
- **PR1 (S)** — fix rail tooltip clipping (`lucky-cat.css`: `overflow:visible` on `.luckycat-primary-rail` + stacking so the `::after` tooltip layers above the inner rail).
- **PR2 (S)** — custom SVG rail icons: new `rail_svg_icon(item)` macro keyed on `item.key`, wired into `rail_icon_link` + `drawer_nav_link`, with the `| icon` glyph as fallback.
- **PR3 (M)** — deploy on free-threaded 3.14t: Dockerfile keeps the slim base + `uv python install 3.14t` (note: `python:3.14t-slim` is **not** a real tag) + `PYTHON_GIL=0` + curated `[ui,sessions,forms]`+chirp-ui (drop `[all]`'s `argon2-cffi`/`asyncpg` — keep itsdangerous+multipart). Makes `/ft/stream` honestly GIL-off.

**Foundation:**
- **PR4 (M)** — pure query seam (no routes): `search.py` (lift `command_palette._matches` → one home), `ranking.py` (`top_gainers/losers/volume` + `market_stats`), `research.py` (frozen `Row`, `build_rows`, `query_catalog(rows, *, q, sector, price_range, change_band, vol_range, sort_key, sort_dir, page, page_size) -> QueryResult`). Stable total-order sorts (key, then symbol) for determinism. **Single source of truth** consumed by Home/Trending/Research.
- **PR8 (M)** — scale prep: env-gated synthetic catalog (default 6 so determinism goldens hold), re-bound the SimFeed ThreadPool (don't spawn N=500 threads), make `_context.context()` lazy/per-view (today it eagerly builds tickers+sparklines for ALL markets on EVERY request — fatal at 500).

**Views:**
- **PR5 (M)** — Trending (`/markets/trending`), depends PR4. Snapshot-per-swap (no live re-rank).
- **PR6 (L)** — Research (`/markets/research`), depends PR4. URL-param-driven (`?q=&sort=&page=`) `Page` shell + `Fragment` swaps; server-side paginate.
- **PR7 (M)** — Home lobby (`/markets` + `/` alias), depends PR4/5/6/9 (so outbound links resolve). De-dupe cards across preview sections (no duplicate DOM ids).

**Tie-it-together:**
- **PR9 (M)** — rail rework to the fixed destinations + `/watchlist` → `/markets/favorites` move + delete dead anchors. Depends PR5/6 (links must resolve) + PR2 (icons for new keys).

## Data layer

One pure seam (PR4), no I/O, frozen dataclasses, deterministic. `query_catalog`
does filter → stable-sort → slice so the template renders only `page_size` rows
regardless of catalog size. Cmd-K and Research both call `search._matches`.

## Open decisions (all have recommendations)

1. **Canonical home** — `/` as an **alias** rendering `/markets` (no redirect), vs a redirect. **Rec: alias** (no round-trip, no `href='/'` churn). *Load-bearing for PR7/PR9.*
2. **Sector source** — a static `SECTORS` map in `research.py` vs a `sector` field on the `Market` dataclass (ripples into the determinism golden + every consumer — stop-and-ask). **Rec: static map.**
3. **500-coin catalog** — env-gated synthetic defs (default 6, goldens green) vs growing `SimFeed._MARKET_DEFS`. **Rec: env-gated synthetic (PR8).**
4. **Protocol scope** — keep query/ranking helpers as pure modules (callers feature-detect) vs add to the `FeedSource` Protocol (every adapter incl. future Kraken/CoinGecko #226 must implement — stop-and-ask). **Rec: keep out of the Protocol.**
5. **Trending live re-rank** — snapshot-per-swap vs an SSE live-reorder. **Rec: snapshot** (live reorder fights htmx swap semantics + churns star state); note a `signal()`-backed version as a future enhancement.
6. **Issue numbers** — assign a child issue per PR under epic #220 (closure-acceptance gate needs `@pytest.mark.issue(N)`).

## Risks / footguns

- **Outlet self-override (FOOTGUN #2):** every Trending segment + Research filter/sort/paginate/search/compare control inherits `hx-target=#main`/`hx-select=#page-content` from the boosted shell; each MUST self-override to its own fragment id (`#movers-region`/`#research-results`) and the fragment route must re-emit that wrapper, or the swap lands empty. Pin with a mandatory test in PR5/PR6.
- **RouteState reserved-segment guard:** `market_detail_active` treats any one-level path under `/markets` as a coin, so `/markets/{favorites,trending,research}` would wrongly pin a coin section. PR9 must guard reserved segments before the detail check.
- **Filesystem-router collision:** `pages/markets/{trending,research}` must resolve as static children, not be captured by `{symbol}`. Prove via `app.check()` + explicit `GET == 200` tests.
- **Determinism goldens:** `test_feed_determinism.py` pins the 6-symbol warmed dict at seed `0xCA7`. The synthetic catalog must stay env-gated (default 6) and all sorts stable.
- **`/watchlist` → `/markets/favorites` href churn:** touches `navigation.py`, `command_palette._ROOMS`, `RouteState`, `watchlist/page.html`, the inner-rail key special-case + OOB target (`sidebar.html`/`app.py`/`_layout.html`), and the `/watchlist/toggle` `HX-Current-URL` literal — coupled edit; the link-crawl catches dead links but not a detached count badge.
- **Home duplicate ids:** a coin in both movers AND watchlist preview duplicates `#luckycat-card-{symbol}` / `#watchlist-star-{symbol}` — de-dupe at render (breaks the no-dup-id invariant + the unstar-prune target otherwise).
- **Deploy-preflight contract (PR3):** the `[all]`→curated change must keep itsdangerous (sessions) + python-multipart (forms) or the app breaks; verify against actual `app.py` imports.

## Doc trail

Update `DESIGN.md` §1 (feature map → Home/Trending/Research/Favorites), §2 (IA
doctrine table → five fixed Markets destinations), §5 (footgun note). Changelog
fragments per user-visible PR. `@pytest.mark.issue(N)` per PR for the closure gate.
Graduate this RFC to `plan/completed/` when shipped.
