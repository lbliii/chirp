"""Thin LLM streaming for chirp.

Provider string in, typed async iterables out. Not a framework.

Basic usage::

    from chirp.ai import LLM, AgentRun

    llm = LLM("anthropic:claude-sonnet-4-20250514")

    # Generate text
    text = await llm.generate("Explain quantum computing simply")

    # Stream unified events
    async for event in llm.stream_events("Analyze this document:"):
        ...

    # Agent loop with tools
    run = AgentRun(llm, app.tools)
    async for event in run.stream("What's the weather?"):
        ...

Requires ``httpx``::

    pip install chirp[ai]
"""

from chirp.ai.agent import AgentRun
from chirp.ai.errors import AIError, ProviderError, ProviderNotInstalledError
from chirp.ai.events import (
    DoneEvent,
    ErrorEvent,
    StreamEvent,
    StreamToolCallEvent,
    StreamToolResultEvent,
    TokenEvent,
)
from chirp.ai.llm import LLM
from chirp.ai.memory import (
    ConversationStore,
    InMemoryConversationStore,
    SessionConversationStore,
)
from chirp.ai.streaming import (
    stream_events_to_fragments,
    stream_to_fragments,
    stream_with_sources,
)

__all__ = [
    "LLM",
    "AIError",
    "AgentRun",
    "ConversationStore",
    "DoneEvent",
    "ErrorEvent",
    "InMemoryConversationStore",
    "ProviderError",
    "ProviderNotInstalledError",
    "SessionConversationStore",
    "StreamEvent",
    "StreamToolCallEvent",
    "StreamToolResultEvent",
    "TokenEvent",
    "stream_events_to_fragments",
    "stream_to_fragments",
    "stream_with_sources",
]
