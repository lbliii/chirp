"""Register app.py routes not covered by filesystem pages."""

from wiring.routes import account, ft, markets_sse, notifications, passkeys, search, watchlist

from chirp import App


def register(app: App) -> None:
    account.register(app)
    watchlist.register(app)
    search.register(app)
    markets_sse.register(app)
    ft.register(app)
    notifications.register(app)
    passkeys.register(app)
