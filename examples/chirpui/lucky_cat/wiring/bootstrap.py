"""Import-time bootstrap — stale-module purge for shared pytest workers (#413).

Called from ``conftest.py`` and ``app.py`` before wiring / ``mount_pages`` so a
sibling example's cached modules cannot shadow this tree on a shared xdist worker.
"""

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_CHIRPUI_ROOT = _ROOT.parent

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
    "passkey_store",
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
        return all(root.resolve() not in Path(str(p)).resolve().parents for p in paths)
    return False


def _prefer_root_on_sys_path(root: Path) -> None:
    """Keep only this example's root at ``sys.path[0]``.

    Every chirpui example exposes a PEP-420 ``pages`` namespace. Leaving a sibling
    example on ``sys.path`` merges namespace ``__path__`` entries and the wrong
    ``pages._context`` wins even after a foreign-only ``sys.modules`` purge.
    """
    root_resolved = root.resolve()
    root_str = str(root_resolved)
    chirpui_resolved = _CHIRPUI_ROOT.resolve()
    for entry in list(sys.path):
        try:
            candidate = Path(entry).resolve()
        except OSError:
            continue
        if (
            candidate.is_dir()
            and candidate.parent == chirpui_resolved
            and candidate != root_resolved
        ):
            while entry in sys.path:
                sys.path.remove(entry)
    while root_str in sys.path:
        sys.path.remove(root_str)
    sys.path.insert(0, root_str)


def purge_stale_sibling_modules(root_dir: Path | None = None) -> None:
    """Drop cached top-level modules from another example on the same xdist worker."""
    root = root_dir or _ROOT
    for name in _SIBLING_MODULES:
        mod = sys.modules.get(name)
        if mod is not None and _module_foreign_to(mod, root):
            del sys.modules[name]

    # ``pages`` is a shared namespace — always drop the whole tree so the next
    # import resolves from *root* alone (foreign-only checks miss merged __path__).
    for name in [n for n in list(sys.modules) if n == "pages" or n.startswith("pages.")]:
        sys.modules.pop(name, None)

    _prefer_root_on_sys_path(root)


def purge_wiring_modules() -> None:
    """Drop cached ``wiring*`` modules so each ``app.py`` reload gets a fresh App."""
    for name in list(sys.modules):
        if name == "wiring" or name.startswith("wiring."):
            sys.modules.pop(name, None)
