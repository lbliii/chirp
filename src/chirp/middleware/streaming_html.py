"""Inject HTML snippets into streamed ``text/html`` bodies before ``</body>``.

Buffered ``Response`` bodies are handled by :class:`HTMLInject`. Streaming
``StreamingResponse`` chunks need a bounded buffer so ``</body>`` split across
chunks is detected without materializing the entire body.
"""

import inspect
import re
from collections.abc import AsyncIterator, Iterator
from typing import cast

_SCRIPT_CHIRP_MARKER = re.compile(
    r"""<script\b[^>]*\bdata-chirp=["']([^"']+)["']""",
    re.IGNORECASE,
)


def _html_has_script_chirp_marker(html: str, chirp_value: str) -> bool:
    return any(match.group(1) == chirp_value for match in _SCRIPT_CHIRP_MARKER.finditer(html))


# If no </body> after this many bytes, stop buffering and pass through (full_page_only).
_MAX_BUFFER_NO_BODY = 2 * 1024 * 1024


async def _chunks_to_async(
    chunks: Iterator[str] | AsyncIterator[str],
) -> AsyncIterator[str]:
    """Normalize sync or async chunk iterators to async iteration."""
    if inspect.isasyncgen(chunks):
        async for c in chunks:
            yield c
        return
    if isinstance(chunks, AsyncIterator):
        async for c in cast(AsyncIterator[str], chunks):
            yield c
        return
    for c in chunks:
        yield c


async def async_stream_inject_before_body(
    chunks: Iterator[str] | AsyncIterator[str],
    *,
    snippet: str,
    before: str = "</body>",
    dedup_marker: str | None = None,
    dedup_script_chirp: str | None = None,
    full_page_only: bool = True,
) -> AsyncIterator[str]:
    """Yield HTML chunks, inserting *snippet* before the first *before* delimiter.

    If *dedup_marker* is set and appears before the first *before*, the stream is
    passed through unchanged (no double injection).

    If *dedup_script_chirp* is set, dedup requires a ``<script data-chirp="…">``
    tag with that value (avoids false positives from page content mentioning the
    marker string).

    If *before* never appears and *full_page_only* is True, the buffered tail is
    yielded as-is (same as :class:`HTMLInject` when ``</body>`` is absent).

    Handles *before* split across chunk boundaries via a bounded buffer.
    """
    buf = ""
    passthrough = False

    async for chunk in _chunks_to_async(chunks):
        if passthrough:
            yield chunk
            continue

        buf += chunk

        while not passthrough:
            i_body = buf.find(before)
            i_dup = -1
            if dedup_script_chirp and _html_has_script_chirp_marker(buf, dedup_script_chirp):
                i_dup = 0
            elif dedup_marker:
                i_dup = buf.find(dedup_marker)

            if i_body != -1:
                if i_dup != -1 and i_dup < i_body:
                    passthrough = True
                    yield buf
                    buf = ""
                    break
                head = buf[:i_body]
                tail = buf[i_body + len(before) :]
                yield head + snippet + before
                buf = ""
                passthrough = True
                if tail:
                    yield tail
                break

            if len(buf) > _MAX_BUFFER_NO_BODY:
                passthrough = True
                yield buf
                buf = ""
                break

            break

    if not passthrough and buf:
        if full_page_only:
            yield buf
        else:
            yield buf + snippet
