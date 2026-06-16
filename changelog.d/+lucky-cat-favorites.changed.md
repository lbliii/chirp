⭐ **Lucky Cat — Markets rail rework + Favorites move (`/watchlist` → `/markets/favorites`).**
The Markets contextual rail is now **four fixed destinations** — Home, Favorites,
Trending, Research — instead of an O(N) one-row-per-market list (the full catalog
lives in Research). On a coin-detail route the current market is pinned in the
rail, and the dead Overview / Order-book / Trades / Info jump anchors are gone.
The starred-markets view moved from `/watchlist` to `/markets/favorites` (one of
the fixed destinations); `/watchlist` now answers a **308 permanent redirect** so
existing bookmarks keep working, and a `RouteState` reserved-segment guard keeps
`/markets/{favorites,trending,research}` from being mistaken for a coin symbol.
