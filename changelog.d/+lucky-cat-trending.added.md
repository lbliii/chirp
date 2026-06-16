🔥 **Lucky Cat — Trending destination (`/markets/trending`).** A new fixed Markets
destination: a movers leaderboard with a segmented Gainers / Losers / Volume
control that swaps a `#movers-region` over htmx (snapshot-per-swap, no live
re-rank). It is backed by the shared `ranking` / `research` query seam, so its
numbers and ordering match the rest of the Markets surfaces. The segment toggles
self-override the boosted shell's inherited outlet (`hx-target` / `hx-select` →
`#movers-region`) and `page.py` re-emits that wrapper — the canonical
boosted-shell local-swap pattern (footgun #2).
