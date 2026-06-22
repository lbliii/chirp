"""Conftest for lucky_cat — loads app.py with the example dir on sys.path."""

import importlib.util
import sys
from pathlib import Path

import pytest

# Keep all Lucky Cat tests on one xdist worker — they mutate sys.path and
# sys.modules["app"] in ways that race when split across workers.
pytestmark = pytest.mark.xdist_group("lucky_cat")

_here = Path(__file__).parent
if str(_here) not in sys.path:
    sys.path.insert(0, str(_here))

from wiring.bootstrap import purge_stale_sibling_modules, purge_wiring_modules


def _purge_wiring_modules() -> None:
    purge_wiring_modules()


@pytest.fixture(autouse=True)
def _lucky_cat_on_path(request: pytest.FixtureRequest):
    """Make the example dir importable for *every* test in this package.

    The ``TestSimFeed`` tests do ``from feed import ...`` in-body without taking
    ``example_app``; without this they'd only pass when an earlier fixture-using
    test happened to run first and leave the dir on ``sys.path`` / ``feed`` in
    ``sys.modules``. This guarantees correctness under ``-k`` selection, single
    tests, ``pytest-randomly``, and ``xdist``. Idempotent with ``example_app``:
    whichever adds the path removes it, never both.
    """
    here = Path(request.path).parent
    added = str(here) not in sys.path
    if added:
        sys.path.insert(0, str(here))
    purge_stale_sibling_modules(here)
    try:
        yield
    finally:
        if added and str(here) in sys.path:
            sys.path.remove(str(here))


@pytest.fixture
def example_app(request: pytest.FixtureRequest):
    """Load app from app.py with the lucky_cat directory on path for feed import."""
    here = Path(request.path).parent
    app_path = here / "app.py"
    module_name = f"example_{here.name}"
    module = None
    prior_app_module = sys.modules.get("app")
    if str(here) not in sys.path:
        sys.path.insert(0, str(here))
    try:
        purge_stale_sibling_modules(here)
        _purge_wiring_modules()
        spec = importlib.util.spec_from_file_location(module_name, app_path)
        assert spec is not None
        assert spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        sys.modules["app"] = module
        spec.loader.exec_module(module)
        # Reset the feed cache for test isolation (#222); next get_feed() rebuilds.
        feed_mod = sys.modules.get("feed")
        if feed_mod is not None and hasattr(feed_mod, "reset"):
            feed_mod.reset()
            feed_mod.get_feed()
        session_mod = sys.modules.get("session_store")
        if session_mod is not None and hasattr(session_mod, "reset"):
            session_mod.reset()
        # Reset the house wallet to its seed balance too (#230 adds reset()).
        wallet_mod = sys.modules.get("wallet")
        if wallet_mod is not None and hasattr(wallet_mod, "reset"):
            wallet_mod.reset()
        account_mod = sys.modules.get("account_store")
        if account_mod is not None and hasattr(account_mod, "reset"):
            account_mod.reset()
        backplane_mod = sys.modules.get("backplane")
        if backplane_mod is not None and hasattr(backplane_mod, "reset"):
            backplane_mod.reset()
        # Reset the trading store (positions / open orders / history) (#225).
        trade_mod = sys.modules.get("trade_store")
        if trade_mod is not None and hasattr(trade_mod, "reset"):
            trade_mod.reset()
        # Reset the notifications log (topbar bell) for test isolation.
        notif_mod = sys.modules.get("notifications")
        if notif_mod is not None and hasattr(notif_mod, "reset"):
            notif_mod.reset()
        # Reset the watchlist (starred markets behind the rail lane) for isolation.
        watch_mod = sys.modules.get("watchlist")
        if watch_mod is not None and hasattr(watch_mod, "reset"):
            watch_mod.reset()
        # Reset the demo user store (the auth account) for test isolation.
        users_mod = sys.modules.get("users")
        if users_mod is not None and hasattr(users_mod, "reset"):
            users_mod.reset()
        yield module.app
    finally:
        if module is not None and sys.modules.get("app") is module:
            if prior_app_module is None:
                del sys.modules["app"]
            else:
                sys.modules["app"] = prior_app_module
        sys.modules.pop(module_name, None)
        if str(here) in sys.path:
            sys.path.remove(str(here))
