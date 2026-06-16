🐱 **Lucky Cat — the Markets lobby is now fully reactive.** The whole board updates
live over the single `/_chirp/live` connection: the stat strip (24h volume /
advancers / decliners) ticks with directional flash, the movers grid (Gainers /
Losers / Volume) re-ranks live, and the featured slot is a bespoke spotlight whose
price + sparkline update and that re-ranks to follow the current top gainer. It is
the canonical *live board* recipe — one source signal (`lobby_snapshot`) samples
the feed on a human cadence and emits a self-contained snapshot, and three
`@app.derived` projections (`market_stats` / `movers` / `featured`) re-render their
regions in lockstep, bound with the new `signal_attrs()` on the existing grid
containers. The featured spotlight no longer reuses the `market_card`
`#luckycat-card` / `#watchlist-star` ids, so it can change symbol live without
colliding with the (static, per-session) watchlist preview.
