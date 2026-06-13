"""Settings → Security — GET /settings/security.

A small security-settings stub. The controls submit back to this GET route
(``method="get"``), so the page is non-mutating — no POST handler, no CSRF
needed, and ``app.check()`` stays clean. Renders into the chirp-ui shell content
block; navigation.py keeps Settings active and lights the inner rail's "Security"
lane (``/settings/security`` href + ``settings_active`` prefix).
"""

from chirp import Page


def get() -> Page:
    return Page("settings/security/page.html", "page_content", page_block_name="page_root")
