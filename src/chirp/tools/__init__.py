"""MCP tool support for chirp.

Register functions as MCP tools alongside HTTP routes. Agents call tools
via JSON-RPC at ``/mcp``, humans interact through the same functions via
HTML routes. Tool calls emit events for real-time dashboards.

Usage::

    from chirp import App, EventStream, Fragment
    from chirp.tools import ToolCallEvent

    app = App()

    @app.tool("search", description="Search inventory")
    async def search(query: str) -> list[dict]:
        return await db.search(query)

    @app.route("/dashboard/feed")
    async def feed(request):
        async def stream():
            async for event in app.tool_events.subscribe():
                yield Fragment("dashboard.html", "row", event=event)
        return EventStream(stream())
"""

from chirp.tools.events import ToolCallEvent, ToolEventBus
from chirp.tools.registry import ToolDef, ToolRegistry

__all__ = [
    "ToolCallEvent",
    "ToolDef",
    "ToolEventBus",
    "ToolRegistry",
]
