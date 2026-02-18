"""Alpine.js script injection — opt-in local UI state support.

Injects the Alpine.js script before ``</body>`` when ``AppConfig(alpine=True)``.
Uses ``defer`` so Alpine runs after DOM parsing; Alpine 3 auto-discovers
elements including those swapped by htmx.

Controlled by ``AppConfig(alpine=True)`` (default: ``False``).
"""


def alpine_snippet(version: str, csp: bool = False) -> str:
    """Build the Alpine.js script tag for injection.

    Args:
        version: Alpine version (e.g. "3.15.8").
        csp: If True, use the CSP-safe build for strict Content-Security-Policy.

    Returns:
        HTML script tag for Alpine.js.
    """
    pkg = "alpinejs" if not csp else "alpinejs/dist/cdn/csp"
    return f'<script defer src="https://unpkg.com/{pkg}@{version}" data-chirp="alpine"></script>'
