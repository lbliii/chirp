🐱 **Lucky Cat — Markets Home is now a curated lobby (`/markets`, with `/` as an
alias).** The old full markets grid landing is retired for a bounded lobby (~9
cards): a stat strip (`ranking.market_stats`), a top-movers preview
(`ranking.top_gainers/losers/volume`, a few each, as links into Trending), a
watchlist preview, a featured market, and a CTA into Research — the full 500+ coin
catalog now lives only in Research. `/` is an **alias** (no redirect) rendering the
SAME `markets/page.html` from one shared `lobby.lobby_context`, so the two routes
can never drift. The card-bearing regions (featured + watchlist preview) are
de-duped at render — the featured symbol is dropped from the watchlist preview so
`#luckycat-card-{symbol}` / `#watchlist-star-{symbol}` never duplicate (the
no-duplicate-id invariant + the `/watchlist/toggle` unstar-prune target). Boosted
in-shell links carry the full `shell_outlet_attrs()` outlet contract.
