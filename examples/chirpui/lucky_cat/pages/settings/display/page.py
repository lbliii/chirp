"""Settings → Display — GET /settings/display.

A small display-settings stub. The controls submit back to this GET route
(``method="get"``), so the page is non-mutating — no POST handler, no CSRF, and
``app.check()`` stays clean. Renders into the chirp-ui shell content block;
navigation.py keeps Settings active and lights the inner rail's "Display" lane
(``/settings/display`` href + ``settings_active`` prefix).
"""

from chirp import Page, login_required


@login_required
def get() -> Page:
    return Page("settings/display/page.html", "page_content", page_block_name="page_root")
