"""Market ranking helpers for Lucky Cat (#277).

The leaderboard math behind the Trending destination (``pages/markets/trending``
— gainers / losers / volume) and the Home lobby stat strip
(``pages/markets``). Operates on the flat :class:`research.Row` view so the
numbers (price / 24h change / notional volume) match every other Markets
surface exactly.

Pure & deterministic: stable total-order sorts (rank key, then symbol ascending
as a tiebreaker), so ``top_gainers(rows, 3)`` is the same tuple every call for
the same input — the snapshot-per-swap Trending segments (RFC: no live re-rank)
stay reproducible and the goldens hold.
"""

from __future__ import annotations

from dataclasses import dataclass

from research import Row


def _ranked(rows: tuple[Row, ...], attr: str, *, descending: bool) -> list[Row]:
    """Stable total-order rank of ``rows`` by ``attr`` then symbol ascending."""
    ordered = sorted(rows, key=lambda r: r.symbol)
    ordered.sort(key=lambda r: getattr(r, attr), reverse=descending)
    return ordered


def top_gainers(rows: tuple[Row, ...], n: int = 5) -> tuple[Row, ...]:
    """The ``n`` rows with the highest 24h change (most positive first)."""
    return tuple(_ranked(rows, "change_pct", descending=True)[:n])


def top_losers(rows: tuple[Row, ...], n: int = 5) -> tuple[Row, ...]:
    """The ``n`` rows with the lowest 24h change (most negative first)."""
    return tuple(_ranked(rows, "change_pct", descending=False)[:n])


def top_volume(rows: tuple[Row, ...], n: int = 5) -> tuple[Row, ...]:
    """The ``n`` rows with the highest notional 24h volume."""
    return tuple(_ranked(rows, "volume", descending=True)[:n])


@dataclass(frozen=True, slots=True)
class MarketStats:
    """Aggregate market snapshot for the Home lobby stat strip.

    ``advancers`` / ``decliners`` count strictly positive / strictly negative
    24h change (a flat coin is neither). ``top_gainer`` / ``top_loser`` are
    ``None`` only for an empty catalog.
    """

    count: int
    total_volume: float
    advancers: int
    decliners: int
    top_gainer: Row | None
    top_loser: Row | None


def market_stats(rows: tuple[Row, ...]) -> MarketStats:
    """Aggregate ``rows`` into the Home stat-strip figures."""
    gainers = top_gainers(rows, 1)
    losers = top_losers(rows, 1)
    return MarketStats(
        count=len(rows),
        total_volume=sum(r.volume for r in rows),
        advancers=sum(1 for r in rows if r.change_pct > 0),
        decliners=sum(1 for r in rows if r.change_pct < 0),
        top_gainer=gainers[0] if gainers else None,
        top_loser=losers[0] if losers else None,
    )
