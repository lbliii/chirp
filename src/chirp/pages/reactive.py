"""Structured reactive templates — automatic SSE push of changed blocks.

Uses kida's static dependency analysis (``DependencyWalker``) to know
which template blocks depend on which context paths.  When a store
mutation changes data, affected blocks are re-rendered via
``render_block()`` and pushed over SSE.

Components:

- ``ChangeEvent``: Emitted by stores after mutations.
- ``ReactiveBus``: Broadcast channel for change events (per-scope).
- ``DependencyIndex``: Maps context paths to block references.
- ``reactive_stream()``: SSE endpoint that auto-pushes affected blocks.

Example::

    # In the store
    bus = ReactiveBus()

    def apply_edit(self, edit: Edit) -> Document | None:
        updated = self._apply_edit_inner(edit)
        if updated:
            bus.emit_sync(ChangeEvent(
                scope=edit.doc_id,
                changed_paths=frozenset({"doc.content", "doc.version"}),
            ))
        return updated

    # In the route
    @app.route("/doc/{doc_id}/live")
    def live(doc_id: str) -> EventStream:
        return reactive_stream(
            bus, scope=doc_id,
            index=dep_index,
            kida_env=env,
            context_builder=lambda: build_context(doc_id),
        )
"""

from __future__ import annotations

import asyncio
import contextlib
import re
import threading
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from kida import Environment

from chirp.realtime.events import EventStream
from chirp.templating.returns import Fragment


# ---------------------------------------------------------------------------
# Change Events
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class ChangeEvent:
    """Emitted by a store after a data mutation.

    Attributes:
        scope: Scope identifier (e.g., a document ID) so subscribers
            only receive events for their scope.
        changed_paths: The set of context paths that changed
            (e.g., ``{"doc.content", "doc.version"}``).
        origin: Opaque identifier for who caused this change (e.g.,
            user ID, session ID).  Used by ``reactive_stream`` to
            skip events originating from the same connection.
            ``None`` means system-initiated — always delivered.
    """

    scope: str
    changed_paths: frozenset[str]
    origin: str | None = None


# ---------------------------------------------------------------------------
# Reactive Event Bus
# ---------------------------------------------------------------------------

class ReactiveBus:
    """Broadcast channel for data change events.

    Thread-safe.  Each call to ``subscribe(scope)`` returns an async
    iterator that yields ``ChangeEvent``s for that scope.  When
    ``emit()`` is called, the event is placed into every matching
    subscriber's queue.

    Modeled on chirp's ``ToolEventBus`` but scoped per-key.
    """

    __slots__ = ("_lock", "_subscribers")

    def __init__(self) -> None:
        # scope -> set of subscriber queues
        self._subscribers: dict[str, set[asyncio.Queue[ChangeEvent | None]]] = {}
        self._lock = threading.Lock()

    def emit_sync(self, event: ChangeEvent) -> None:
        """Broadcast a change event synchronously (from any thread).

        Uses ``put_nowait`` so it never blocks.  Drops the event for
        a subscriber if its queue is full (back-pressure).
        """
        with self._lock:
            queues = set(self._subscribers.get(event.scope, set()))
        for queue in queues:
            with contextlib.suppress(asyncio.QueueFull):
                queue.put_nowait(event)

    async def emit(self, event: ChangeEvent) -> None:
        """Broadcast a change event (async version)."""
        self.emit_sync(event)

    async def subscribe(self, scope: str) -> AsyncIterator[ChangeEvent]:
        """Subscribe to change events for a specific scope.

        Yields ``ChangeEvent`` objects as they are emitted.  The
        subscription is automatically cleaned up when the iterator
        exits (client disconnects).
        """
        queue: asyncio.Queue[ChangeEvent | None] = asyncio.Queue(maxsize=256)
        with self._lock:
            self._subscribers.setdefault(scope, set()).add(queue)
        try:
            while True:
                event = await queue.get()
                if event is None:
                    break
                yield event
        finally:
            with self._lock:
                scope_set = self._subscribers.get(scope)
                if scope_set is not None:
                    scope_set.discard(queue)
                    if not scope_set:
                        del self._subscribers[scope]

    def close(self, scope: str | None = None) -> None:
        """Signal subscribers to stop.

        If *scope* is given, only close that scope's subscribers.
        Otherwise close all.
        """
        with self._lock:
            if scope is not None:
                queues = self._subscribers.pop(scope, set())
            else:
                queues = set()
                for s in list(self._subscribers):
                    queues |= self._subscribers.pop(s)
        for queue in queues:
            with contextlib.suppress(asyncio.QueueFull):
                queue.put_nowait(None)


# ---------------------------------------------------------------------------
# Dependency Index
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class BlockRef:
    """Reference to a renderable block within a template.

    Attributes:
        template_name: Kida template name.
        block_name: Block name within the template.
        dom_id: DOM element ID to target for OOB swap.
            Defaults to the block name.
    """

    template_name: str
    block_name: str
    dom_id: str | None = None

    @property
    def target_id(self) -> str:
        """DOM element ID for OOB targeting."""
        return self.dom_id or self.block_name


@dataclass(frozen=True, slots=True)
class _SSESwapElement:
    """Parsed info about an HTML element with ``sse-swap``."""

    swap_event: str
    dom_id: str | None
    inner_block: str | None  # first {% block NAME %} inside element


# Regex: element open tag with sse-swap attribute, capturing everything
# up to the close of the tag.
_SSE_SWAP_ELEM_RE = re.compile(
    r"<(?P<tag>\w+)\b(?P<attrs>[^>]*)>",
    re.IGNORECASE,
)

_SSE_SWAP_ATTR_RE = re.compile(
    r'\bsse-swap\s*=\s*["\']([^"\']+)["\']',
    re.IGNORECASE,
)

_ID_ATTR_RE = re.compile(
    r'\bid\s*=\s*["\']([^"\']+)["\']',
    re.IGNORECASE,
)

_BLOCK_TAG_RE = re.compile(
    r"\{%-?\s*block\s+(\w+)",
)


def _extract_sse_swap_elements(source: str) -> list[_SSESwapElement]:
    """Extract elements with ``sse-swap`` and find their associated blocks.

    For each ``<tag ... sse-swap="event" ...>`` found, captures the swap
    event name, element ``id``, and the associated ``{% block NAME %}``.

    Handles two common patterns:

    1. **Block inside element** (block is a child)::

           <span id="status" sse-swap="status">
               {% block toolbar_status %}v{{ doc.version }}{% endblock %}
           </span>

    2. **Block wraps element** (block is the parent)::

           {% block toolbar_status %}
           <span id="status" sse-swap="status">v{{ doc.version }}</span>
           {% endblock %}
    """
    results: list[_SSESwapElement] = []

    for match in _SSE_SWAP_ELEM_RE.finditer(source):
        attrs = match.group("attrs")
        tag = match.group("tag").lower()

        swap_match = _SSE_SWAP_ATTR_RE.search(attrs)
        if not swap_match:
            continue

        swap_event = swap_match.group(1)

        id_match = _ID_ATTR_RE.search(attrs)
        dom_id = id_match.group(1) if id_match else None

        inner_block: str | None = None

        # Strategy 1: Look for {% block %} INSIDE the element.
        start = match.end()
        close_tag = "</" + tag
        close_idx = source.lower().find(close_tag, start)
        if close_idx == -1:
            inner = source[start:]
        else:
            inner = source[start:close_idx]

        block_match = _BLOCK_TAG_RE.search(inner)
        if block_match:
            inner_block = block_match.group(1)

        # Strategy 2: Look for {% block %} BEFORE the element (wrapping).
        # Search the ~200 chars preceding the element's open tag for
        # the nearest {% block NAME %} that hasn't been closed yet.
        if inner_block is None:
            lookback = source[max(0, match.start() - 200):match.start()]
            # Find the LAST {% block NAME %} in the lookback window.
            # If there's a matching {% endblock %} after it, it's closed.
            all_blocks = list(_BLOCK_TAG_RE.finditer(lookback))
            if all_blocks:
                candidate = all_blocks[-1]
                # Verify the block isn't closed before our element
                after_candidate = lookback[candidate.end():]
                if "endblock" not in after_candidate:
                    inner_block = candidate.group(1)

        results.append(_SSESwapElement(
            swap_event=swap_event,
            dom_id=dom_id,
            inner_block=inner_block,
        ))

    return results


class DependencyIndex:
    """Maps context paths to the template blocks that depend on them.

    Built at app startup from kida's ``BlockMetadata.depends_on`` sets.
    Thread-safe after construction (read-only).

    Example::

        index = DependencyIndex()
        index.register_template(env, "doc/{doc_id}/_layout.html")
        affected = index.affected_blocks({"doc.version"})
        # -> [BlockRef("doc/{doc_id}/_layout.html", "toolbar")]
    """

    __slots__ = ("_path_to_blocks",)

    def __init__(self) -> None:
        # context_path -> list of BlockRef
        self._path_to_blocks: dict[str, list[BlockRef]] = {}

    def register_template(
        self,
        env: Environment,
        template_name: str,
        *,
        block_names: list[str] | None = None,
        dom_id_map: dict[str, str] | None = None,
    ) -> None:
        """Register a template's blocks into the dependency index.

        Uses kida's static analysis to extract dependencies.

        Args:
            env: Kida environment.
            template_name: Template to analyze.
            block_names: If given, only register these blocks.
                Otherwise all blocks are registered.
            dom_id_map: Mapping of block_name -> DOM element ID.
                If a block isn't in this map, block_name is used.
        """
        template = env.get_template(template_name)
        metadata = template.block_metadata()
        dom_ids = dom_id_map or {}

        for name, block_meta in metadata.items():
            if block_names is not None and name not in block_names:
                continue
            ref = BlockRef(
                template_name=template_name,
                block_name=name,
                dom_id=dom_ids.get(name),
            )
            for dep_path in block_meta.depends_on:
                self._path_to_blocks.setdefault(dep_path, []).append(ref)

    def register_from_sse_swaps(
        self,
        env: Environment,
        template_name: str,
        template_source: str,
        *,
        exclude_blocks: set[str] | None = None,
    ) -> int:
        """Auto-register blocks that have matching ``sse-swap`` elements.

        Scans the raw template source for elements with both ``sse-swap``
        and ``id`` attributes, finds the ``{% block %}`` inside each,
        and registers only those blocks — with the correct ``dom_id``
        mapping.

        Blocks listed in *exclude_blocks* are skipped (e.g.,
        client-managed ``contenteditable`` blocks that should never be
        re-rendered via SSE).

        Returns the number of blocks auto-registered.

        Example::

            index = DependencyIndex()
            source = env.loader.get_source(env, "page.html")[0]
            n = index.register_from_sse_swaps(env, "page.html", source)
            # Registers only blocks inside sse-swap elements
        """
        exclude = exclude_blocks or set()

        # 1. Find elements with sse-swap (and optionally id)
        #    Pattern: <tag ... sse-swap="event" ... id="dom_id" ...>
        #    or:      <tag ... id="dom_id" ... sse-swap="event" ...>
        sse_swap_elements = _extract_sse_swap_elements(template_source)

        if not sse_swap_elements:
            return 0

        # 2. For each sse-swap element, find the {% block %} inside it.
        #    Convention: the block is a direct child of the element.
        block_to_dom_id: dict[str, str] = {}
        block_to_event: dict[str, str] = {}

        for elem in sse_swap_elements:
            block_name = elem.inner_block
            if block_name is None or block_name in exclude:
                continue
            if elem.dom_id:
                block_to_dom_id[block_name] = elem.dom_id
            block_to_event[block_name] = elem.swap_event

        if not block_to_dom_id:
            return 0

        # 3. Register via the standard method (uses kida static analysis)
        self.register_template(
            env,
            template_name,
            block_names=list(block_to_dom_id),
            dom_id_map=block_to_dom_id,
        )

        return len(block_to_dom_id)

    def affected_blocks(self, changed_paths: frozenset[str]) -> list[BlockRef]:
        """Find all blocks affected by a set of changed context paths.

        Also checks parent paths: if ``"doc.version"`` changed and a
        block depends on ``"doc"``, it's considered affected.

        Returns:
            List of unique ``BlockRef`` objects.
        """
        seen: set[tuple[str, str]] = set()
        result: list[BlockRef] = []

        for changed in changed_paths:
            # Direct match
            for ref in self._path_to_blocks.get(changed, []):
                key = (ref.template_name, ref.block_name)
                if key not in seen:
                    seen.add(key)
                    result.append(ref)

            # Check if any registered path is a prefix of the changed path
            # e.g., block depends on "doc", changed_paths includes "doc.version"
            for registered_path, refs in self._path_to_blocks.items():
                if changed.startswith(registered_path + ".") or registered_path.startswith(
                    changed + "."
                ):
                    for ref in refs:
                        key = (ref.template_name, ref.block_name)
                        if key not in seen:
                            seen.add(key)
                            result.append(ref)

        return result


# ---------------------------------------------------------------------------
# Reactive SSE Stream
# ---------------------------------------------------------------------------

def reactive_stream(
    bus: ReactiveBus,
    *,
    scope: str,
    index: DependencyIndex,
    context_builder: Callable[[], dict[str, Any] | Awaitable[dict[str, Any]]],
    origin: str | None = None,
    kida_env: Any = None,
) -> EventStream:
    """Create an SSE EventStream that auto-pushes re-rendered blocks.

    Subscribes to the ``ReactiveBus`` for the given scope.  When a
    ``ChangeEvent`` arrives, looks up affected blocks in the
    ``DependencyIndex`` and yields them as ``Fragment`` objects.
    The chirp SSE layer handles rendering via the app's kida env.

    Args:
        bus: The reactive event bus to subscribe to.
        scope: Scope key (e.g., document ID).
        index: Dependency index mapping paths to blocks.
        context_builder: Callable that returns the current context dict
            (called after each change to get fresh data).
        origin: Identity of this connection (e.g., user/session ID).
            Events whose ``origin`` matches are skipped — the client
            that caused the change doesn't need to be notified of it.
            ``None`` disables origin filtering.
        kida_env: Deprecated — rendering is handled by the SSE response
            layer.  Accepted for backwards compatibility.

    Returns:
        An ``EventStream`` ready to be returned from a route handler.

    Example::

        @app.route("/doc/{doc_id}/live")
        def live(doc_id: str) -> EventStream:
            return reactive_stream(
                bus, scope=doc_id, index=dep_index,
                context_builder=lambda: {"doc": store.get(doc_id)},
                origin=session_id,
            )
    """
    import inspect

    async def generate() -> AsyncIterator[Fragment]:
        async for change in bus.subscribe(scope):
            # Skip events we caused (both must be non-None and equal)
            if origin is not None and change.origin == origin:
                continue

            blocks = index.affected_blocks(change.changed_paths)
            if not blocks:
                continue

            # Build fresh context
            ctx = context_builder()
            if inspect.isawaitable(ctx):
                ctx = await ctx

            for ref in blocks:
                yield Fragment(
                    ref.template_name,
                    ref.block_name,
                    target=ref.target_id,
                    **ctx,
                )

    return EventStream(generate())
