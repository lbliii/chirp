"""Live invocation log — bridge ``ToolEventBus`` into an ``EventStream``.

Orrery-style consoles (and any MCP host) subscribe to tool-call events and
stream each one as a named-block ``Fragment`` over SSE. No historical
persistence — this is a live fan-out of the existing bus only.

Usage::

    from chirp.tools.live_log import mount_invocation_log, tool_event_stream

    mount_invocation_log(app)  # GET /invocations/live

    # or hand-roll a route:
    @app.route("/feed", referenced=True)
    def feed():
        return tool_event_stream(app.tool_events)
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import TYPE_CHECKING

from chirp.realtime.events import EventStream
from chirp.templating.returns import Fragment
from chirp.tools.events import ToolEventBus

if TYPE_CHECKING:
    from chirp.app import App

#: Default SSE path for the live invocation log.
DEFAULT_INVOCATION_LOG_PATH = "/invocations/live"

#: Default template name registered by :func:`mount_invocation_log`.
DEFAULT_INVOCATION_LOG_TEMPLATE = "chirp_invocation_log.html"

#: Named block yielded for each ``ToolCallEvent``.
DEFAULT_INVOCATION_LOG_BLOCK = "invocation_row"

#: DOM id of the live-log sink in the packaged fragment template.
DEFAULT_INVOCATION_LOG_TARGET = "chirp-invocation-log"


def _invocation_log_template_source(*, connect_path: str) -> str:
    """Build the packaged live-log template (row fragment + optional sink shell).

    The ``invocation_row`` block is what the SSE stream yields. The
    ``invocation_log`` block is a ready-to-embed sink for console pages
    (sibling #982) — it is not a full page and carries no browse/keystore UI.
    """
    # Paths are framework-owned constants; escape quotes for attribute safety.
    path = connect_path.replace('"', "")
    return f"""\
{{% block {DEFAULT_INVOCATION_LOG_BLOCK} %}}
<div class="chirp-invocation-row" data-call-id="{{{{ event.call_id }}}}">
  <span class="tool-name">{{{{ event.tool_name }}}}</span>
  <span class="call-id">{{{{ event.call_id }}}}</span>
  <span class="call-args">{{{{ event.arguments }}}}</span>
</div>
{{% end %}}

{{% block invocation_log %}}
<div id="{DEFAULT_INVOCATION_LOG_TARGET}"
     hx-ext="sse"
     sse-connect="{path}"
     hx-disinherit="hx-target hx-swap">
  <div sse-swap="message" hx-target="this" hx-swap="afterbegin"></div>
</div>
{{% end %}}
"""


def tool_event_stream(
    bus: ToolEventBus,
    *,
    template: str = DEFAULT_INVOCATION_LOG_TEMPLATE,
    block: str = DEFAULT_INVOCATION_LOG_BLOCK,
    target: str | None = None,
) -> EventStream:
    """Bridge ``bus.subscribe()`` into an ``EventStream`` of live-log fragments.

    Each successful tool invocation already emits a :class:`ToolCallEvent` on
    the app's :class:`ToolEventBus`. This helper turns that subscription into
    the standard Chirp SSE return type so consoles can ``sse-connect`` without
    hand-rolling the generator.
    """

    async def generate() -> AsyncIterator[Fragment]:
        async for event in bus.subscribe():
            yield Fragment(
                template,
                block,
                event=event,
                target=target,
            )

    return EventStream(generate())


def mount_invocation_log(
    app: App,
    *,
    path: str = DEFAULT_INVOCATION_LOG_PATH,
    template: str = DEFAULT_INVOCATION_LOG_TEMPLATE,
    block: str = DEFAULT_INVOCATION_LOG_BLOCK,
    bus: ToolEventBus | None = None,
) -> str:
    """Register the live invocation-log SSE route and its fragment template.

    Adds a ``DictLoader`` entry for ``template`` (row + optional sink shell)
    and a ``referenced=True`` GET route that returns
    :func:`tool_event_stream` over ``bus`` (default: ``app.tool_events``).

    Returns the normalized route path.
    """
    from kida import DictLoader

    normalized = _normalize_path(path)
    event_bus = bus if bus is not None else app.tool_events

    app.add_loader(
        DictLoader(
            {
                template: _invocation_log_template_source(connect_path=normalized),
            }
        )
    )

    @app.route(normalized, methods=["GET"], name="chirp_invocation_log", referenced=True)
    def invocation_log() -> EventStream:
        return tool_event_stream(event_bus, template=template, block=block)

    return normalized


def _normalize_path(path: str) -> str:
    if not isinstance(path, str) or not path.strip():
        msg = "invocation log path must be a non-empty string"
        raise ValueError(msg)
    normalized = path.strip()
    if not normalized.startswith("/"):
        normalized = "/" + normalized
    if len(normalized) > 1 and normalized.endswith("/"):
        normalized = normalized.rstrip("/")
    return normalized


__all__ = [
    "DEFAULT_INVOCATION_LOG_BLOCK",
    "DEFAULT_INVOCATION_LOG_PATH",
    "DEFAULT_INVOCATION_LOG_TARGET",
    "DEFAULT_INVOCATION_LOG_TEMPLATE",
    "mount_invocation_log",
    "tool_event_stream",
]
