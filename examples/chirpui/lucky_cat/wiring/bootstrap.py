"""Import-time bootstrap — stale-module purge for shared pytest workers (#413).

Called from ``conftest.py`` before loading ``app.py``, not from the app entrypoint.
"""

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent

_SIBLING_MODULES = (
    "feed",
    "store",
    "wallet",
    "account_store",
    "backplane",
    "session_store",
    "shell",
    "navigation",
    "trade_store",
    "notifications",
    "watchlist",
    "users",
)


def _module_foreign_to(mod, root: Path) -> bool:
    """True when *mod* was loaded from outside *root* (another example on the worker)."""
    mod_file = getattr(mod, "__file__", None)
    if mod_file is not None:
        try:
            return root.resolve() not in Path(mod_file).resolve().parents
        except OSError:
            return True
    mod_path = getattr(mod, "__path__", None)
    if mod_path is not None:
        paths = mod_path if isinstance(mod_path, (list, tuple)) else [mod_path]
        return all(
            root.resolve() not in Path(str(p)).resolve().parents for p in paths
        )
    return False


def purge_stale_sibling_modules(root_dir: Path | None = None) -> None:
    """Drop cached top-level modules from another example on the same xdist worker."""
    root = root_dir or _ROOT
    for name in _SIBLING_MODULES:
        mod = sys.modules.get(name)
        if mod is not None and _module_foreign_to(mod, root):
            del sys.modules[name]

    for name in [n for n in list(sys.modules) if n == "pages" or n.startswith("pages.")]:
        mod = sys.modules.get(name)
        if mod is not None and _module_foreign_to(mod, root):
            del sys.modules[name]


def purge_wiring_modules() -> None:
    """Drop cached ``wiring*`` modules so each ``app.py`` reload gets a fresh App."""
    for name in list(sys.modules):
        if name == "wiring" or name.startswith("wiring."):
            sys.modules.pop(name, None)
