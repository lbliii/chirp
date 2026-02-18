"""ASGI response sending — translates chirp Response types to ASGI messages.

Handles both standard single-body responses and chunked streaming responses.
"""

import logging
from collections.abc import AsyncIterator

from chirp._internal.asgi import Send
from chirp.http.response import Response, StreamingResponse

logger = logging.getLogger("chirp.server")


def _body_allowed(status: int) -> bool:
    """Whether an HTTP status code permits a response body."""
    # RFC: 1xx, 204, and 304 responses do not include a message body.
    return not (100 <= status < 200 or status in {204, 304})


async def send_response(response: Response, send: Send) -> None:
    """Translate a chirp Response into ASGI send() calls."""
    # Build raw headers
    raw_headers: list[tuple[bytes, bytes]] = [
        (b"content-type", response.content_type.encode("latin-1")),
    ]
    for name, value in response.headers:
        raw_headers.append((name.lower().encode("latin-1"), value.encode("latin-1")))
    raw_headers.extend(
        (b"set-cookie", cookie.to_header_value().encode("latin-1")) for cookie in response.cookies
    )

    body = response.body_bytes if _body_allowed(response.status) else b""

    raw_headers.append((b"content-length", str(len(body)).encode("latin-1")))

    await send(
        {
            "type": "http.response.start",
            "status": response.status,
            "headers": raw_headers,
        }
    )
    await send(
        {
            "type": "http.response.body",
            "body": body,
        }
    )


async def send_streaming_response(
    response: StreamingResponse,
    send: Send,
    *,
    debug: bool = False,
) -> None:
    """Send a streaming response via chunked transfer encoding.

    Sends headers immediately, then each chunk as an ASGI body
    message with ``more_body=True``. Closes with an empty body.
    On mid-stream error, emits an HTML comment and closes.
    """
    raw_headers: list[tuple[bytes, bytes]] = [
        (b"content-type", response.content_type.encode("latin-1")),
        (b"transfer-encoding", b"chunked"),
    ]
    for name, value in response.headers:
        raw_headers.append((name.lower().encode("latin-1"), value.encode("latin-1")))

    # No content-length — chunked transfer encoding signals body boundaries
    await send(
        {
            "type": "http.response.start",
            "status": response.status,
            "headers": raw_headers,
        }
    )

    def _encode_chunk(chunk: str | bytes) -> bytes:
        return chunk.encode("utf-8") if isinstance(chunk, str) else chunk

    try:
        if isinstance(response.chunks, AsyncIterator):
            async for chunk in response.chunks:
                if chunk:
                    await send(
                        {
                            "type": "http.response.body",
                            "body": _encode_chunk(chunk),
                            "more_body": True,
                        }
                    )
        else:
            for chunk in response.chunks:
                if chunk:
                    await send(
                        {
                            "type": "http.response.body",
                            "body": _encode_chunk(chunk),
                            "more_body": True,
                        }
                    )
    except Exception as exc:
        # Mid-stream error: log with structured formatting, emit visible error
        import sys

        from chirp.server.terminal_errors import _is_kida_error, log_error

        log_error(exc)

        if debug:
            # Visible error div instead of invisible HTML comment
            import traceback

            error_msg = (
                (lambda e: getattr(e, "format_compact", lambda: str(e))())(exc)
                if _is_kida_error(exc)
                else traceback.format_exc()
            )
            # Escape HTML in the error message
            escaped = error_msg.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            error_chunk = (
                '<div class="chirp-error" data-status="500"'
                f' style="white-space:pre-wrap;font-family:monospace;'
                f'padding:1em;background:#1a1b26;color:#c0caf5;border:2px solid #f7768e">'
                f"{escaped}</div>"
            )
        else:
            error_chunk = "<!-- chirp: render error -->"
        await send(
            {
                "type": "http.response.body",
                "body": error_chunk.encode("utf-8"),
                "more_body": True,
            }
        )
        # Re-store exception info for any caller that needs it
        sys.exc_info()

    # Close the stream
    await send(
        {
            "type": "http.response.body",
            "body": b"",
            "more_body": False,
        }
    )
