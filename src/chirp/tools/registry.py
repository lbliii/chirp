"""Tool registry — compiled tool table with dispatch.

Mirrors the ``Router`` + ``Route`` pattern from ``chirp.routing``:
``ToolDef`` is the frozen definition (like ``Route``), ``ToolRegistry``
is the compiled lookup table (like ``Router``).

Free-threading safety:
    - ToolDef is a frozen dataclass (immutable)
    - ToolRegistry._tools is a dict built at freeze time, never mutated
    - ToolEventBus handles its own synchronization
"""

import inspect
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from chirp.tools.events import ToolCallEvent, ToolEventBus
from chirp.tools.schema import function_to_schema


@dataclass(frozen=True, slots=True)
class ToolDef:
    """A frozen tool definition.

    Created during app setup, compiled into the registry at freeze time.
    """

    name: str
    description: str
    handler: Callable[..., Any]
    schema: dict[str, Any]


class ToolRegistry:
    """Compiled tool table. Created at freeze time, immutable at runtime.

    Provides ``list_tools()`` for MCP ``tools/list`` and ``call_tool()``
    for MCP ``tools/call`` dispatch.
    """

    __slots__ = ("_event_bus", "_tools")

    def __init__(
        self,
        tools: list[ToolDef],
        event_bus: ToolEventBus,
    ) -> None:
        self._tools: dict[str, ToolDef] = {t.name: t for t in tools}
        self._event_bus = event_bus

    def list_tools(self) -> list[dict[str, Any]]:
        """Return MCP-formatted tool list for ``tools/list`` response."""
        return [
            {
                "name": tool.name,
                "description": tool.description,
                "inputSchema": tool.schema,
            }
            for tool in self._tools.values()
        ]

    async def call_tool(
        self,
        name: str,
        arguments: dict[str, Any],
    ) -> Any:
        """Dispatch a tool call by name.

        Calls the handler with the provided arguments, emits a
        ``ToolCallEvent`` on success, and returns the result.

        Raises ``KeyError`` if the tool name is not registered.
        """
        tool = self._tools.get(name)
        if tool is None:
            msg = f"Tool not found: {name!r}"
            raise KeyError(msg)

        # Call the handler with matched arguments
        result = tool.handler(**arguments)
        if inspect.isawaitable(result):
            result = await result

        # Emit event for dashboard subscribers
        event = ToolCallEvent(
            tool_name=name,
            arguments=arguments,
            result=result,
            timestamp=time.time(),
        )
        await self._event_bus.emit(event)

        return result

    def get(self, name: str) -> ToolDef | None:
        """Look up a tool by name. Returns ``None`` if not found."""
        return self._tools.get(name)

    def __len__(self) -> int:
        return len(self._tools)

    def __contains__(self, name: str) -> bool:
        return name in self._tools


def compile_tools(
    pending: list[tuple[str, str, Callable[..., Any]]],
    event_bus: ToolEventBus,
) -> ToolRegistry:
    """Compile pending tool registrations into a frozen ToolRegistry.

    Called during ``App._freeze()``. Each tuple is ``(name, description, handler)``.
    Schema generation happens here so errors surface at startup, not at runtime.
    """
    tools: list[ToolDef] = []
    seen_names: set[str] = set()

    for name, description, handler in pending:
        if name in seen_names:
            msg = f"Duplicate tool name: {name!r}"
            raise ValueError(msg)
        seen_names.add(name)

        schema = function_to_schema(handler)
        tools.append(
            ToolDef(
                name=name,
                description=description,
                handler=handler,
                schema=schema,
            )
        )

    return ToolRegistry(tools, event_bus)
