"""ASGI response sending — translates chirp Response types to ASGI messages.

Handles both standard single-body responses and chunked streaming responses.
"""

from collections.abc import AsyncIterator

from chirp._internal.asgi import Send
from chirp.http.response import Response, StreamingResponse


async def send_response(response: Response, send: Send) -> None:
    """Translate a chirp Response into ASGI send() calls."""
    # Build raw headers
    raw_headers: list[tuple[bytes, bytes]] = [
        (b"content-type", response.content_type.encode("latin-1")),
    ]
    for name, value in response.headers:
        raw_headers.append((name.lower().encode("latin-1"), value.encode("latin-1")))
    raw_headers.extend(
        (b"set-cookie", cookie.to_header_value().encode("latin-1"))
        for cookie in response.cookies
    )

    body = response.body_bytes

    raw_headers.append((b"content-length", str(len(body)).encode("latin-1")))

    await send({
        "type": "http.response.start",
        "status": response.status,
        "headers": raw_headers,
    })
    await send({
        "type": "http.response.body",
        "body": body,
    })


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
    ]
    for name, value in response.headers:
        raw_headers.append((name.lower().encode("latin-1"), value.encode("latin-1")))

    # No content-length for chunked transfer
    await send({
        "type": "http.response.start",
        "status": response.status,
        "headers": raw_headers,
    })

    try:
        if isinstance(response.chunks, AsyncIterator):
            async for chunk in response.chunks:
                if chunk:
                    await send({
                        "type": "http.response.body",
                        "body": chunk.encode("utf-8"),
                        "more_body": True,
                    })
        else:
            for chunk in response.chunks:
                if chunk:
                    await send({
                        "type": "http.response.body",
                        "body": chunk.encode("utf-8"),
                        "more_body": True,
                    })
    except Exception:
        # Mid-stream error: emit HTML comment and close
        import traceback

        if debug:
            tb = traceback.format_exc()
            error_chunk = f"<!-- chirp: render error\n{tb}\n-->"
        else:
            error_chunk = "<!-- chirp: render error -->"
        await send({
            "type": "http.response.body",
            "body": error_chunk.encode("utf-8"),
            "more_body": True,
        })

    # Close the stream
    await send({
        "type": "http.response.body",
        "body": b"",
        "more_body": False,
    })
