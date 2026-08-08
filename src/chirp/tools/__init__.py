"""MCP tool support for chirp.

Register functions as MCP tools alongside HTTP routes. Agents call tools
via JSON-RPC at ``/mcp``, humans interact through the same functions via
HTML routes. Tool calls emit events for real-time dashboards.

Usage::

    from chirp import App
    from chirp.tools import mount_invocation_log

    app = App()

    @app.tool("search", description="Search inventory")
    async def search(query: str) -> list[dict]:
        return await db.search(query)

    # Live ToolEventBus → EventStream bridge (console / Orrery)
    mount_invocation_log(app)
"""

from chirp.tools.approval import (
    InMemoryToolApprovalStore,
    PendingToolApproval,
    SessionToolApprovalStore,
    ToolApprovalError,
    ToolApprovalStore,
)
from chirp.tools.events import ToolCallEvent, ToolEventBus
from chirp.tools.live_log import (
    DEFAULT_INVOCATION_LOG_BLOCK,
    DEFAULT_INVOCATION_LOG_PATH,
    DEFAULT_INVOCATION_LOG_TARGET,
    DEFAULT_INVOCATION_LOG_TEMPLATE,
    mount_invocation_log,
    tool_event_stream,
)
from chirp.tools.registry import ToolDef, ToolRegistry

__all__ = [
    "DEFAULT_INVOCATION_LOG_BLOCK",
    "DEFAULT_INVOCATION_LOG_PATH",
    "DEFAULT_INVOCATION_LOG_TARGET",
    "DEFAULT_INVOCATION_LOG_TEMPLATE",
    "InMemoryToolApprovalStore",
    "PendingToolApproval",
    "SessionToolApprovalStore",
    "ToolApprovalError",
    "ToolApprovalStore",
    "ToolCallEvent",
    "ToolDef",
    "ToolEventBus",
    "ToolRegistry",
    "mount_invocation_log",
    "tool_event_stream",
]
