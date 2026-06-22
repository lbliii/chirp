"""Register app.py routes not covered by filesystem pages."""
from chirp import App

from wiring.routes import account, ft, markets_sse, notifications, search, watchlist


def register(app: App) -> None:
    account.register(app)
    watchlist.register(app)
    search.register(app)
    markets_sse.register(app)
    ft.register(app)
    notifications.register(app)
