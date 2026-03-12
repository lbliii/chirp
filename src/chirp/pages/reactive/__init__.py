"""Structured reactive templates — automatic SSE push of changed blocks."""

from chirp.pages.reactive.bus import ReactiveBus
from chirp.pages.reactive.events import BlockRef, ChangeEvent
from chirp.pages.reactive.index import DependencyIndex
from chirp.pages.reactive.stream import reactive_stream

__all__ = [
    "BlockRef",
    "ChangeEvent",
    "DependencyIndex",
    "ReactiveBus",
    "reactive_stream",
]
