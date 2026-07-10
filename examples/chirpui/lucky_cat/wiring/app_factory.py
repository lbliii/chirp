"""App factory — ROOT_DIR, config, app, signal emit seam, ChirpUI registration. DESIGN.md §7."""

import sys
from dataclasses import replace
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import session_store
from backplane import bind_emit, get_backplane
from navigation import active_route_path, route_state, shell_navigation
from shell import rail_is_collapsed

from chirp import App, AppConfig, use_chirp_ui
from chirp.middleware.static import StaticFiles

PAGES_DIR = ROOT_DIR / "pages"
STATIC_DIR = ROOT_DIR / "static"

# CHIRP — DESIGN.md

_base = AppConfig.from_env()
config = replace(
    _base,
    template_dir=PAGES_DIR,
    worker_mode="async",
    workers=1,  # Demo: in-memory state + one /_chirp/live pin — DESIGN.md §7
    # view_transitions="htmx" animates the boosted #main swap on navigation.
    # Keep htmx unset (the chirp-ui shell bundles it) and do NOT add alpine=True
    # (use_chirp_ui owns Alpine — adding it would double-inject).
    view_transitions="htmx",
    secret_key=_base.secret_key or "dev-only-not-for-production",
    passkeys=True,
)

app = App(config=config)

# Signal publication seam; App.emit owns memory/Redis transport (DESIGN.md §7).
bind_emit(app.emit)


def _signal_audience_key() -> str:
    """The store key for session-scoped signal fan-out (empty for the test default)."""
    key = session_store.session_key()
    return "" if key == session_store.DEFAULT_KEY else key


def emit_signal(name: str, value, *, audience_key: str | None = None) -> None:
    """Push a signal value through the configured backplane (default: in-process)."""
    aud = _signal_audience_key() if audience_key is None else audience_key
    get_backplane().publish(name, value, audience_key=aud)


def fan_out_notifications_live() -> None:
    """Emit each *real* session's bell snapshot over its scoped /_chirp/live topic.

    ``notifications`` is session-scoped, so every emit must target a real session
    key: the framework forbids an empty ``audience_key`` on a session signal (a
    ``ValueError`` that would kill the source pump for the whole connection). The
    DEFAULT_KEY/anonymous bucket has no live audience — anonymous visitors carry
    only global signals and keep their SSR-seeded bell — so ``client_keys()``
    (non-default keys only) skips it instead of coercing it to ``""``.
    """
    import notifications

    for key in session_store.client_keys():
        with session_store.bind(key):
            emit_signal("notifications", notifications.snapshot(), audience_key=key)


def register_chirp_ui() -> None:
    """Wire ChirpUI, static files, and template globals."""
    use_chirp_ui(app)
    app.add_middleware(StaticFiles(directory=STATIC_DIR, prefix="/static"))

    # CHIRP — DESIGN.md

    app.template_global()(route_state)
    app.template_global()(shell_navigation)
    app.template_global()(active_route_path)
    # Server-side rail-collapse preference — read in the layout's head_extra to
    # pre-render the collapsed state (no FOUC) and cookie-persisted by
    # static/lucky-cat-shell.js.
    app.template_global()(rail_is_collapsed)
