"""Request-scoped shell preferences for the Lucky Cat app chrome (#231, part 2).

The progressive rail collapses the inner contextual rail down to the bare icon
rail, and that preference is *cookie-persisted* and read **server-side** so the
collapsed state is baked into the very first paint — no flash-of-uncollapsed-rail
(FOUC). Ported (stripped of the forum domain) from elbysodic's ``shell.py``.

The cookie names are namespaced (``luckycat_rail_collapsed`` / ``luckycat_rail_width``)
so they do NOT collide with chirp-ui's own ``chirpui-sidebar-collapsed`` localStorage
key nor elbysodic's ``elbysodic_sidebar_hidden_v2``. The matching client drag-resizer
lives in ``static/lucky-cat-shell.js``; the matching pre-sized CSS gate lives in the
layout's ``head_extra``.

BUILD 2 (the genuine drag-resize) adds a second persisted preference — the *inner-rail
width* in CSS px. It too is read server-side (:func:`rail_width`) and emitted as a
pre-sized ``:root { --luckycat-rail-width: <clamped>px }`` so a dragged width survives
a reload with no flash. The cookie is an untrusted client value echoed into a
server-rendered ``<style>``, so :func:`rail_width` numerically parses and clamps it to
the same ``[MIN, MAX]`` px range the JS drag enforces — a non-numeric or out-of-range
cookie is rejected, never reflected into CSS.
"""

from __future__ import annotations

from chirp.context import get_request
from chirp.http.request import Request

#: Namespaced cookie name + values "true"/"false" (string). Do NOT collide with
#: chirp-ui's ``chirpui-sidebar-collapsed`` (localStorage) or elbysodic's key.
RAIL_COLLAPSED_COOKIE = "luckycat_rail_collapsed"

#: Namespaced cookie holding the dragged inner-rail width in CSS px (string int).
RAIL_WIDTH_COOKIE = "luckycat_rail_width"

#: The class the client JS toggles on ``.chirpui-app-shell`` to collapse the rail.
RAIL_COLLAPSED_CLASS = "luckycat-rail--collapsed"

#: Inner-rail width drag clamp (CSS px). Mirrors the JS clamp + the resize handle's
#: ``aria-valuemin``/``aria-valuemax`` so server, client, and ARIA never disagree.
RAIL_WIDTH_MIN_PX = 176
RAIL_WIDTH_MAX_PX = 416


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


def rail_width(request: Request | None = None) -> int | None:
    """Return the persisted inner-rail width (CSS px) for this request, or ``None``.

    Read server-side so the layout can pre-size the rail on first paint (no FOUC
    flash from a JS-only width). Returns ``None`` when there is no request in
    scope, no cookie, or the cookie is invalid — the layout then falls back to the
    CSS default width.

    SECURITY: the cookie is an untrusted client value that the layout reflects into
    a server-rendered ``<style>``. We parse it as an int and clamp it to
    ``[RAIL_WIDTH_MIN_PX, RAIL_WIDTH_MAX_PX]``; a non-numeric value is rejected
    (``None``), so nothing but a bounded integer can ever reach the CSS sink.
    """
    if request is None:
        try:
            request = get_request()
        except LookupError:
            return None
    raw = request.cookies.get(RAIL_WIDTH_COOKIE)
    if raw is None:
        return None
    try:
        value = int(raw)
    except ValueError, TypeError:
        return None
    return max(RAIL_WIDTH_MIN_PX, min(RAIL_WIDTH_MAX_PX, value))
