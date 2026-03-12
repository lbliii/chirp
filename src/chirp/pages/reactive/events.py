"""Change events, block references, and SSE swap element extraction."""

from __future__ import annotations

import re
from dataclasses import dataclass


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
        inner = source[start:] if close_idx == -1 else source[start:close_idx]

        block_match = _BLOCK_TAG_RE.search(inner)
        if block_match:
            inner_block = block_match.group(1)

        # Strategy 2: Look for {% block %} BEFORE the element (wrapping).
        # Search the ~200 chars preceding the element's open tag for
        # the nearest {% block NAME %} that hasn't been closed yet.
        if inner_block is None:
            lookback = source[max(0, match.start() - 200) : match.start()]
            # Find the LAST {% block NAME %} in the lookback window.
            # If there's a matching {% endblock %} after it, it's closed.
            all_blocks = list(_BLOCK_TAG_RE.finditer(lookback))
            if all_blocks:
                candidate = all_blocks[-1]
                # Verify the block isn't closed before our element
                after_candidate = lookback[candidate.end() :]
                if "endblock" not in after_candidate:
                    inner_block = candidate.group(1)

        results.append(
            _SSESwapElement(
                swap_event=swap_event,
                dom_id=dom_id,
                inner_block=inner_block,
            )
        )

    return results
