"""AI streaming helpers for SSE + Fragment pattern.

Provides ergonomic wrappers around the core pattern of streaming LLM
tokens as re-rendered HTML fragments via Server-Sent Events.

The fundamental pattern::

    async def generate():
        text = ""
        async for token in llm.stream(prompt):
            text += token
            yield Fragment("chat.html", "response", text=text)
    return EventStream(generate())

This module wraps that pattern into reusable helpers so common cases
are one-liners while keeping the underlying primitives accessible.
"""

from collections.abc import AsyncIterator, Callable
from typing import Any


def extract_markdown_units(buffer: str) -> tuple[str, str]:
    """Extract complete markdown units from a buffer. Returns (complete, in_progress).

    Complete units are full lines (or full code blocks). In-progress is the last
    incomplete part (mid-line or inside an unclosed code block). Use this for
    server-side chunked markdown rendering: render only complete units to avoid
    partial-syntax artifacts.
    """
    if not buffer:
        return ("", "")

    lines = buffer.split("\n")
    in_code = False
    complete_lines: list[str] = []
    i = 0

    while i < len(lines):
        line = lines[i]
        if in_code:
            complete_lines.append(line)
            if line.strip().startswith("```"):
                in_code = False
            i += 1
            continue
        if line.strip().startswith("```"):
            in_code = True
            complete_lines.append(line)
            i += 1
            continue
        complete_lines.append(line)
        i += 1

    if in_code:
        return ("", "\n".join(complete_lines))

    if len(complete_lines) <= 1:
        return ("", buffer)

    return ("\n".join(complete_lines[:-1]), complete_lines[-1])


def stream_to_fragments(
    tokens: AsyncIterator[str],
    template_name: str,
    block_name: str,
    /,
    *,
    context_key: str = "text",
    extra_context: dict[str, Any] | None = None,
) -> AsyncIterator[Any]:
    """Wrap an LLM token stream as a Fragment-yielding async generator.

    Accumulates tokens and yields a ``Fragment`` with the accumulated text
    after each token. The Fragment re-renders the named block with the
    current text, which htmx swaps into the DOM.

    Usage::

        from chirp import EventStream
        from chirp.ai import LLM
        from chirp.ai.streaming import stream_to_fragments

        llm = LLM("anthropic:claude-sonnet-4-20250514")

        @app.route("/chat", methods=["POST"])
        async def chat(request: Request):
            prompt = (await request.form())["prompt"]
            fragments = stream_to_fragments(
                llm.stream(prompt),
                "chat.html", "response",
            )
            return EventStream(fragments)

    Args:
        tokens: Async iterator of string tokens (from ``llm.stream()``).
        template_name: Kida template containing the target block.
        block_name: Name of the block to re-render with each update.
        context_key: Template variable name for the accumulated text.
            Defaults to ``"text"``.
        extra_context: Additional template variables passed to every
            Fragment render (e.g., user info, metadata).

    Yields:
        ``Fragment`` instances with progressively accumulated text.
    """
    # Deferred import to avoid circular dependency
    from chirp.templating.returns import Fragment

    return _stream_fragments(
        tokens, template_name, block_name,
        context_key=context_key,
        extra_context=extra_context or {},
        fragment_cls=Fragment,
    )


async def _stream_fragments(
    tokens: AsyncIterator[str],
    template_name: str,
    block_name: str,
    *,
    context_key: str,
    extra_context: dict[str, Any],
    fragment_cls: type,
) -> AsyncIterator[Any]:
    """Internal generator that accumulates tokens and yields Fragments."""
    accumulated = ""
    async for token in tokens:
        accumulated += token
        yield fragment_cls(
            template_name,
            block_name,
            **{context_key: accumulated, **extra_context},
        )


def stream_with_sources(
    tokens: AsyncIterator[str],
    template_name: str,
    *,
    response_block: str = "response",
    sources_block: str | None = None,
    sources: Any = None,
    context_key: str = "text",
    extra_context: dict[str, Any] | None = None,
    share_link_block: str | None = None,
    on_complete: Callable[[str, Any, dict[str, Any]], Any] | None = None,
    chunk_renderer: Callable[[str], str] | None = None,
) -> AsyncIterator[Any]:
    """Stream LLM tokens as fragments, optionally prefixed with a sources block.

    Common RAG pattern: send retrieved sources first (immediate), then
    stream the AI response progressively.

    Usage::

        @app.route("/ask", methods=["POST"])
        async def ask(request: Request):
            question = (await request.form())["question"]
            docs = await db.fetch(Document, "SELECT ... WHERE match(?)", question)
            return EventStream(stream_with_sources(
                llm.stream(f"Context: {docs}\\nQ: {question}"),
                "ask.html",
                sources_block="sources",
                sources=docs,
                response_block="answer",
            ))

    Args:
        tokens: Async iterator of string tokens (from ``llm.stream()``).
        template_name: Kida template containing the target blocks.
        response_block: Block name for the streaming response.
        sources_block: Block name for the sources (rendered once, first).
        sources: Context value passed to the sources block.
        context_key: Template variable name for accumulated text.
        extra_context: Additional context for all Fragment renders.
    """
    from chirp.templating.returns import Fragment

    return _stream_with_sources_impl(
        tokens,
        template_name,
        response_block=response_block,
        sources_block=sources_block,
        sources=sources,
        context_key=context_key,
        extra_context=extra_context or {},
        share_link_block=share_link_block,
        on_complete=on_complete,
        chunk_renderer=chunk_renderer,
        fragment_cls=Fragment,
    )


async def _stream_with_sources_impl(
    tokens: AsyncIterator[str],
    template_name: str,
    *,
    response_block: str,
    sources_block: str | None,
    sources: Any,
    context_key: str,
    extra_context: dict[str, Any],
    share_link_block: str | None,
    on_complete: Callable[[str, Any, dict[str, Any]], Any] | None,
    chunk_renderer: Callable[[str], str] | None,
    fragment_cls: type,
) -> AsyncIterator[Any]:
    """Internal: yield sources fragment, then stream response fragments."""
    # Phase 1: Send sources block (immediate, one-shot)
    if sources_block and sources is not None:
        yield fragment_cls(
            template_name,
            sources_block,
            target=sources_block,
            sources=sources,
            **extra_context,
        )

    # Phase 2: Stream response tokens as fragments
    accumulated = ""
    base_ctx: dict[str, Any] = {**extra_context}
    if sources is not None:
        base_ctx["sources"] = sources

    if chunk_renderer:
        rendered_html = ""
        rendered_markdown = ""
        async for token in tokens:
            accumulated += token
            complete, in_progress = extract_markdown_units(accumulated)
            if complete and (not rendered_markdown or complete.startswith(rendered_markdown)):
                new_markdown = complete[len(rendered_markdown) :]
                if new_markdown:
                    rendered_html += chunk_renderer(new_markdown)
                    rendered_markdown = complete
            yield fragment_cls(
                template_name,
                response_block,
                target=response_block,
                streaming=True,
                rendered_html=rendered_html,
                in_progress=in_progress,
                **base_ctx,
            )
        if accumulated:
            yield fragment_cls(
                template_name,
                response_block,
                target=response_block,
                streaming=False,
                **{context_key: accumulated, **base_ctx},
            )
    else:
        async for token in tokens:
            accumulated += token
            yield fragment_cls(
                template_name,
                response_block,
                target=response_block,
                streaming=True,
                **{context_key: accumulated, **base_ctx},
            )
        if accumulated:
            yield fragment_cls(
                template_name,
                response_block,
                target=response_block,
                streaming=False,
                **{context_key: accumulated, **base_ctx},
            )
    if share_link_block and on_complete:
        share_slug = await on_complete(accumulated, sources, extra_context)
        if share_slug:
            yield fragment_cls(
                template_name,
                share_link_block,
                target=share_link_block,
                share_id=share_slug,
                share_url=f"/share/{share_slug}",
            )
