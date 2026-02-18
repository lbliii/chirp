"""Shared source protocols and types.

A *source* is anything that produces typed data — a database, an LLM, a file
watcher, a message queue. Sources have two modes:

- **fetch**: produce a complete result (``await source.fetch()``)
- **stream**: produce results incrementally (``async for item in source.stream()``)

Both modes yield frozen dataclasses. The template engine (kida) renders them
identically regardless of origin. A ``User`` from Postgres and a ``Summary``
from Claude are both just frozen dataclasses in a template context.

This module defines the shared vocabulary that ``chirp.data`` and ``chirp.ai``
build on. Application code rarely imports from here directly.
"""

from collections.abc import AsyncIterator, Awaitable
from typing import Protocol, runtime_checkable

# -- Type aliases for source results --

# A value that will resolve to T (already resolved or awaitable)
type Pending[T] = T | Awaitable[T]

# A value that can be iterated async (streaming cursor, token stream)
type AsyncSource[T] = AsyncIterator[T]


# -- Protocols --


@runtime_checkable
class Fetchable[T](Protocol):
    """A source that can produce a complete typed result."""

    async def fetch(self) -> list[T]: ...


@runtime_checkable
class Streamable[T](Protocol):
    """A source that can produce results incrementally."""

    def stream(self) -> AsyncIterator[T]: ...


@runtime_checkable
class Source[T](Fetchable[T], Streamable[T], Protocol):
    """A source that supports both fetch and stream access."""
