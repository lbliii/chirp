"""Watchlist — GET redirect + POST /watchlist/toggle (cross-page star control)."""

import watchlist
from feed import get_feed
from navigation import active_route_path

from chirp import Fragment, OOB, Redirect, Request, login_required

from wiring.app_factory import app


def register(app_instance) -> None:
    @app_instance.route("/watchlist", name="watchlist.moved")
    def watchlist_moved():
        return Redirect("/markets/favorites", status=308)

    @app_instance.route("/watchlist/toggle", methods=["POST"], name="watchlist.toggle")
    @login_required
    async def watchlist_toggle(request: Request):
        feed = get_feed()
        form = await request.form()
        symbol = (form.get("symbol") or "").strip()
        known = (
            feed.has_symbol(symbol)
            if hasattr(feed, "has_symbol")
            else any(m.symbol == symbol for m in feed.markets())
        )
        starred = watchlist.contains(symbol) if not symbol or not known else watchlist.toggle(symbol)
        fragments: list[Fragment] = [
            Fragment(
                "_components/market.html",
                "watchlist_star_swap",
                symbol=symbol,
                starred=starred,
            ),
            Fragment(
                "_layout.html",
                "watchlist_count_swap",
                target="watchlist-count",
                watchlist_count=watchlist.count(),
            ),
        ]
        if symbol and known and not starred:
            current_url = request.headers.get("HX-Current-URL", "")
            if active_route_path(current_url) == "/markets/favorites":
                fragments.append(
                    Fragment(
                        "_components/market.html",
                        "watchlist_card_remove",
                        symbol=symbol,
                    )
                )
        return OOB(*fragments)
