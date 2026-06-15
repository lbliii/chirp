"""Request-scoped shell preferences for the Lucky Cat app chrome (#231).

The progressive rail collapses the inner contextual rail down to the bare icon
rail, and that preference is *cookie-persisted* and read **server-side** so the
collapsed state is baked into the very first paint — no flash-of-uncollapsed-rail
(FOUC). Ported (stripped of the forum domain) from elbysodic's ``shell.py``.

The cookie name is namespaced (``luckycat_rail_collapsed``) so it does NOT
collide with chirp-ui's own ``chirpui-sidebar-collapsed`` localStorage key nor
elbysodic's ``elbysodic_sidebar_hidden_v2``. The matching client collapse toggle
lives in ``static/lucky-cat-shell.js``; the matching pre-collapse CSS gate lives
in the layout's ``head_extra``.

Collapse is a click-toggle, not a continuous drag-resizer: a first-class
resizable rail belongs in the chirp-ui peer package, not hand-rolled in an
example (see #231's locked decision).
"""

from __future__ import annotations

from chirp.context import get_request
from chirp.http.request import Request

#: Namespaced cookie name + values "true"/"false" (string). Do NOT collide with
#: chirp-ui's ``chirpui-sidebar-collapsed`` (localStorage) or elbysodic's key.
RAIL_COLLAPSED_COOKIE = "luckycat_rail_collapsed"

#: The class the client JS toggles on ``.chirpui-app-shell`` to collapse the rail.
RAIL_COLLAPSED_CLASS = "luckycat-rail--collapsed"


def rail_is_collapsed(request: Request | None = None) -> bool:
    """Return the persisted inner-rail collapse preference for this request.

    Read server-side so the layout can pre-render the collapsed state (no FOUC).
    Defaults to ``False`` (expanded) when there is no request in scope or no
    cookie. Registered as a template global in ``app.py`` so the layout's
    ``head_extra`` can gate the pre-collapse ``<style>`` on it.
    """
    if request is None:
        try:
            request = get_request()
        except LookupError:
            return False
    return request.cookies.get(RAIL_COLLAPSED_COOKIE) == "true"
