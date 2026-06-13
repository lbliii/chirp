"""Command-palette search model for the Lucky Cat shell.

A Cmd/Ctrl-K palette is the single biggest "pro app" signal, so Lucky Cat ships
one composed over chirp-ui's ``command_palette`` component (the native
``<dialog>`` + ``chirpuiDialogTarget`` Alpine controller that opens on
Cmd/Ctrl-K and closes on Escape / backdrop click for free).

This module is the pure-Python data + filtering seam — no I/O, frozen
dataclasses, mirroring ``navigation.py``. The layout populates the palette with
two result groups:

* **Markets** — every market from ``feed.markets()`` (label ``"BTC-MEOW ·
  Bitcoin"`` → href ``/markets/{symbol}``).
* **Go to** — the five persistent rooms (Markets / Portfolio / Trade / Activity
  / Settings), the same destinations the outer icon rail owns.

:func:`palette_results` filters both groups by a case-insensitive substring
query (matching the visible label, the symbol, or the room key) so typing
narrows the list. An empty query returns everything (the resting palette shows
the full directory). Results are returned as typed :class:`PaletteGroup` /
:class:`PaletteItem` trees with empty groups pruned, so the results template
never renders a bare group header.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PaletteItem:
    """One navigable command-palette result.

    ``href`` is always an in-app route so the boosted shell outlet (target
    ``#main``, select ``#page-content``) can swap it, and the deterministic
    ``test_links`` crawl can verify it resolves. ``hint`` renders a small
    right-aligned secondary label (e.g. the room kind or the market base).
    """

    label: str
    href: str
    hint: str = ""


@dataclass(frozen=True, slots=True)
class PaletteGroup:
    """A labelled group of palette results (``label`` heads the group)."""

    label: str
    items: tuple[PaletteItem, ...]


# The persistent "rooms" — the same five destinations the outer icon rail owns
# (navigation._PRIMARY_ROOMS), so the palette and the rail never disagree about
# where you can go. (key, label, href, hint) — key feeds substring matching.
_ROOMS: tuple[tuple[str, str, str, str], ...] = (
    ("markets", "Markets", "/", "Trading floor"),
    ("portfolio", "Portfolio", "/portfolio", "Holdings & P&L"),
    ("trade", "Trade", "/trade", "Place an order"),
    ("activity", "Activity", "/activity", "Fills & deposits"),
    ("settings", "Settings", "/settings", "Profile & display"),
    # Watchlist is the one genuinely-functional non-room destination (a real page
    # behind the Markets-room filter lane). The ⌘K palette is the "go anywhere"
    # surface, so it must reach it too — without this, a user could jump to every
    # room + market but not their starred view. Kept in the Go-to group (matching
    # its rail placement under the Markets room); "watchlist"/"starred" feed the
    # substring match.
    ("watchlist starred", "Watchlist", "/watchlist", "Starred markets"),
)


def _matches(query: str, *haystacks: str) -> bool:
    """True when every whitespace-separated query token is a substring of at
    least one haystack (case-insensitive). An empty query matches everything."""
    q = query.strip().lower()
    if not q:
        return True
    hay = " ".join(haystacks).lower()
    return all(token in hay for token in q.split())


def palette_results(markets: tuple, query: str = "") -> tuple[PaletteGroup, ...]:
    """Filter the markets + rooms directories by ``query``.

    ``markets`` is the ``feed.markets()`` tuple (each item exposes ``symbol`` +
    ``display_name``). Empty groups are pruned so the results template never
    shows a header with nothing under it.
    """
    market_items = tuple(
        PaletteItem(
            label=f"{m.symbol} · {m.display_name}",
            href=f"/markets/{m.symbol}",
            hint=m.base,
        )
        for m in markets
        if _matches(query, m.symbol, m.display_name)
    )
    room_items = tuple(
        PaletteItem(label=label, href=href, hint=hint)
        for key, label, href, hint in _ROOMS
        if _matches(query, key, label)
    )
    groups = (
        PaletteGroup(label="Markets", items=market_items),
        PaletteGroup(label="Go to", items=room_items),
    )
    return tuple(g for g in groups if g.items)
