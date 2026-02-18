"""Thin LLM streaming for chirp.

Provider string in, typed async iterables out. Not a framework.

Basic usage::

    from chirp.ai import LLM

    llm = LLM("anthropic:claude-sonnet-4-20250514")

    # Generate text
    text = await llm.generate("Explain quantum computing simply")

    # Stream text
    async for token in llm.stream("Analyze this document:"):
        print(token, end="")

    # Structured output (frozen dataclass)
    summary = await llm.generate(Summary, prompt="Summarize: ...")

Requires ``httpx``::

    pip install chirp[ai]
"""

from chirp.ai.errors import AIError, ProviderError, ProviderNotInstalledError
from chirp.ai.llm import LLM
from chirp.ai.streaming import stream_to_fragments, stream_with_sources

__all__ = [
    "LLM",
    "AIError",
    "ProviderError",
    "ProviderNotInstalledError",
    "stream_to_fragments",
    "stream_with_sources",
]
