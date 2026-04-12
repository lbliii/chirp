"""Structured reactive templates — automatic SSE push of changed blocks."""

from chirp.pages.reactive.bus import ReactiveBus
from chirp.pages.reactive.events import BlockRef, ChangeEvent, ConnectionInfo
from chirp.pages.reactive.index import DependencyIndex
from chirp.pages.reactive.stream import reactive_stream

__all__ = [
    "BlockRef",
    "ChangeEvent",
    "ConnectionInfo",
    "DependencyIndex",
    "ReactiveBus",
    "reactive_stream",
]
