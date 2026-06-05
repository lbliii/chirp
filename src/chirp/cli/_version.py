"""``chirp --version`` — report chirp and key dependency versions.

A stale install is invisible until it errors at runtime (e.g. a missing
``url_for`` template global from a chirp predating that feature). ``chirp
--version`` surfaces the installed chirp version alongside its tightly coupled
runtime dependencies — kida and pounce — plus the Python build, so a mismatched
environment is obvious before it bites.

The version string mirrors the Environment panel on the debug error page
(``chirp.server.debug.renderers``).
"""

import sys


def _dist_version(dist_name: str, module_name: str | None = None) -> str:
    """Resolve an installed distribution version, falling back to ``__version__``.

    Prefer package metadata (authoritative, no import side effects). If the
    distribution is not installed under that name — e.g. an editable checkout on
    ``PYTHONPATH`` with no metadata — fall back to importing the module and
    reading ``__version__``.
    """
    from importlib.metadata import PackageNotFoundError, version

    try:
        return version(dist_name)
    except PackageNotFoundError:
        if module_name is not None:
            try:
                module = __import__(module_name)
            except ImportError:
                return "unknown"
            return getattr(module, "__version__", "unknown")
        return "unknown"


def version_report() -> str:
    """Build the one-line ``chirp --version`` report.

    Example::

        chirp 0.7.1 (kida 0.10.0, bengal-pounce 0.7.1, Python 3.14.2)
    """
    import chirp

    chirp_version = getattr(chirp, "__version__", "unknown")
    kida_version = _dist_version("kida-templates", "kida")
    pounce_version = _dist_version("bengal-pounce", "pounce")
    python_version = sys.version.split()[0]
    return (
        f"chirp {chirp_version} "
        f"(kida {kida_version}, bengal-pounce {pounce_version}, "
        f"Python {python_version})"
    )
