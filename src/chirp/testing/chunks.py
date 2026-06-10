"""In-process ASGI chunk capture for streaming-response assertions.

``TestClient.request()`` joins every ``http.response.body`` ASGI message into a
single buffered :class:`~chirp.http.response.Response`, which is the right shape
for ordinary handlers but erases the *framing* of a streaming response. For
``Stream`` / ``TemplateStream`` / ``Suspense`` the boundaries between body
messages are load-bearing — they are the difference between a progressive,
shell-first render and a fully buffered one.

:class:`CapturedStream` preserves that framing: it records the ordered list of
non-empty body chunks exactly as the ASGI ``send()`` callable received them
(one entry per ``http.response.body`` message), so a test can assert that a
response arrives as more than one chunk, that the shell bytes precede the
deferred/streamed-block bytes, and that specific markers land in the expected
chunk.

This is a socket-free counterpart to a real chunked-transfer client: the same
``send()`` messages an ASGI server would write to the wire, captured in memory.
Real socket binding is unavailable in the CI sandbox, so structural and ordering
assertions live here; wall-clock timing assertions do not (they need a socket
and are flaky).
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class CapturedStream:
    """The ordered body chunks captured from a single ASGI response.

    Returned by :meth:`chirp.testing.TestClient.request_chunks` (and the
    ``*_chunks`` convenience wrappers). Each entry in :attr:`chunks` is the
    decoded body of one ``http.response.body`` ASGI message with a non-empty
    body, in send order. The terminal empty close message is not recorded.

    For a buffered :class:`~chirp.http.response.Response` this is a single
    chunk; for a streaming response it is one chunk per flushed boundary
    (Suspense shell + one chunk per deferred block, ``Stream``/``TemplateStream``
    flush boundaries, etc.).
    """

    #: Ordered decoded body chunks, one per non-empty ``http.response.body``.
    chunks: tuple[str, ...]
    status: int = 200
    #: Response headers as a case-insensitive-lookup friendly tuple of pairs.
    headers: tuple[tuple[str, str], ...] = ()
    #: ``True`` when the response was sent as a streaming body (the sender used
    #: ``more_body=True``), ``False`` for a single buffered body message.
    streaming: bool = False
    #: Raw byte chunks, parallel to :attr:`chunks`, for binary/marker checks.
    raw_chunks: tuple[bytes, ...] = field(default=())

    @property
    def text(self) -> str:
        """The full response body, all chunks joined in order."""
        return "".join(self.chunks)

    @property
    def chunk_count(self) -> int:
        """Number of non-empty body chunks captured."""
        return len(self.chunks)

    def index_of(self, marker: str) -> int:
        """Return the index of the first chunk containing *marker*.

        Raises ``AssertionError`` if no chunk contains the marker — this is a
        test helper, so a missing marker is a failed expectation, not a silent
        ``-1``.
        """
        for i, chunk in enumerate(self.chunks):
            if marker in chunk:
                return i
        msg = f"marker {marker!r} not found in any of {self.chunk_count} chunk(s)"
        raise AssertionError(msg)

    def header(self, name: str, default: str | None = None) -> str | None:
        """First header value matching *name* (case-insensitive)."""
        target = name.lower()
        for hname, hvalue in self.headers:
            if hname.lower() == target:
                return hvalue
        return default
