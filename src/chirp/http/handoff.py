"""UI-neutral hypermedia handoff helpers Chirp owns.

Covers the minimal browser-facing contract for shell and fragment responses:

- focus target / fallback after swaps
- document title and history (HX-Push-Url / HX-Replace-Url)
- announcements via a live region OOB payload
- OOB transport helpers that compose with existing shell regions

These helpers do not prescribe component classes or a theme. Focus movement is
delivered as an ``HX-Trigger-After-Settle`` event (``chirp:focus``) consumed by
``chirp-handoff.js`` — a CSP-safe external script, not inline handlers.
RFC 017 focus/live-region policy is the accessibility input; this module does
not invent a competing contract system.
"""

from __future__ import annotations

import html
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Any, Literal

from chirp.shell_regions import (
    ANNOUNCEMENTS_ELEMENT_ID,
    DOCUMENT_TITLE_ELEMENT_ID,
    FOCUS_FALLBACK_DEFAULT,
)

if TYPE_CHECKING:
    from chirp.http.response import Response

__all__ = [
    "ANNOUNCEMENTS_ELEMENT_ID",
    "CHIRP_FOCUS_EVENT",
    "DOCUMENT_TITLE_ELEMENT_ID",
    "FOCUS_FALLBACK_DEFAULT",
    "AnnouncementHandoff",
    "FocusHandoff",
    "HypermediaHandoff",
    "TitleHandoff",
    "announce_oob_html",
    "apply_handoff",
    "focus_trigger_payload",
    "handoff_oob_html",
    "title_oob_html",
]

CHIRP_FOCUS_EVENT = "chirp:focus"


@dataclass(frozen=True, slots=True)
class FocusHandoff:
    """Focus destination after an HTMX settle (or full-page equivalent).

    ``target`` is a CSS selector for the preferred focus destination.
    ``fallback`` is used when the target is missing (default ``#main``, which
    Chirp shells mark ``tabindex="-1"`` when they own an outlet).
    """

    target: str | None = None
    fallback: str = FOCUS_FALLBACK_DEFAULT


@dataclass(frozen=True, slots=True)
class TitleHandoff:
    """Document title update, optionally paired with history headers."""

    title: str
    element_id: str = DOCUMENT_TITLE_ELEMENT_ID
    push_url: str | bool | None = None
    replace_url: str | bool | None = None


@dataclass(frozen=True, slots=True)
class AnnouncementHandoff:
    """Live-region announcement payload for HTMX OOB (or full-page seed)."""

    message: str
    politeness: Literal["polite", "assertive"] = "polite"
    region_id: str = ANNOUNCEMENTS_ELEMENT_ID


@dataclass(frozen=True, slots=True)
class HypermediaHandoff:
    """Bundle of Chirp-owned handoff intents for one response."""

    focus: FocusHandoff | None = None
    title: TitleHandoff | None = None
    announcement: AnnouncementHandoff | None = None


def focus_trigger_payload(focus: FocusHandoff) -> dict[str, Any]:
    """Return the ``HX-Trigger-After-Settle`` payload for ``chirp:focus``."""
    return {
        CHIRP_FOCUS_EVENT: {
            "target": focus.target or "",
            "fallback": focus.fallback or FOCUS_FALLBACK_DEFAULT,
        }
    }


def title_oob_html(title: TitleHandoff | str, *, element_id: str | None = None) -> str:
    """Render a ``<title>`` OOB fragment for document title updates."""
    if isinstance(title, str):
        text = title
        eid = element_id or DOCUMENT_TITLE_ELEMENT_ID
    else:
        text = title.title
        eid = element_id or title.element_id
    return (
        f'<title id="{html.escape(eid, quote=True)}" hx-swap-oob="true">{html.escape(text)}</title>'
    )


def announce_oob_html(
    announcement: AnnouncementHandoff | str,
    *,
    politeness: Literal["polite", "assertive"] = "polite",
    region_id: str = ANNOUNCEMENTS_ELEMENT_ID,
) -> str:
    """Render a live-region OOB fragment that replaces announcement text."""
    if isinstance(announcement, str):
        msg = announcement
        live = politeness
        rid = region_id
    else:
        msg = announcement.message
        live = announcement.politeness
        rid = announcement.region_id
    return (
        f'<div id="{html.escape(rid, quote=True)}" '
        f'data-chirp-live-region role="status" '
        f'aria-live="{html.escape(live, quote=True)}" aria-atomic="true" '
        f'hx-swap-oob="innerHTML">{html.escape(msg)}</div>'
    )


def handoff_oob_html(handoff: HypermediaHandoff) -> str:
    """Concatenate OOB markup for title and announcement handoffs."""
    parts: list[str] = []
    if handoff.title is not None:
        parts.append(title_oob_html(handoff.title))
    if handoff.announcement is not None:
        parts.append(announce_oob_html(handoff.announcement))
    return "\n".join(parts)


def apply_handoff(response: Response, handoff: HypermediaHandoff) -> Response:
    """Apply handoff headers and append OOB markup to a buffered Response.

    Full-page responses still receive title OOB (harmless no-op if the element
    is already the document title) and announcement OOB when requested. Focus
    and history headers are HTMX-oriented; plain navigations ignore them.
    """
    result = response
    if handoff.focus is not None:
        result = result.with_hx_trigger_after_settle(focus_trigger_payload(handoff.focus))
    if handoff.title is not None:
        if handoff.title.push_url is not None:
            result = result.with_hx_push_url(handoff.title.push_url)
        if handoff.title.replace_url is not None:
            result = result.with_hx_replace_url(handoff.title.replace_url)
    oob = handoff_oob_html(handoff)
    if not oob:
        return result
    body = result.body
    if isinstance(body, bytes):
        text = body.decode("utf-8")
        sep = "\n" if text and not text.endswith("\n") else ""
        return replace(result, body=(text + sep + oob).encode("utf-8"))
    text = body if isinstance(body, str) else str(body)
    sep = "\n" if text and not text.endswith("\n") else ""
    return replace(result, body=text + sep + oob)
