"""ASGI response sending — translates chirp Response types to ASGI messages.

Handles both standard single-body responses and chunked streaming responses.
"""

import logging
from collections.abc import AsyncIterator
from contextvars import Token
from types import MappingProxyType
from typing import Any, cast

from chirp._internal.asgi import Send
from chirp.context import request_var
from chirp.http.response import FileResponse, Response, StreamingResponse
from chirp.logging import request_id_var

logger = logging.getLogger("chirp.server")

# Immutable mapping for free-threading (no module-level mutable dicts)
_CT_PREENCODED: MappingProxyType[str, bytes] = MappingProxyType(
    {
        "text/html; charset=utf-8": b"text/html; charset=utf-8",
        "application/json; charset=utf-8": b"application/json; charset=utf-8",
        "application/octet-stream": b"application/octet-stream",
        "text/plain; charset=utf-8": b"text/plain; charset=utf-8",
        "application/javascript; charset=utf-8": b"application/javascript; charset=utf-8",
        "text/css; charset=utf-8": b"text/css; charset=utf-8",
    }
)


def _encode_content_type(ct: str) -> bytes:
    return _CT_PREENCODED.get(ct) or ct.encode("latin-1")


def _body_allowed(status: int) -> bool:
    """Whether an HTTP status code permits a response body."""
    # RFC: 1xx, 204, and 304 responses do not include a message body.
    return not (100 <= status < 200 or status in {204, 304})


async def send_response(
    response: Response,
    send: Send,
    *,
    request_id: str | None = None,
) -> None:
    """Translate a chirp Response into ASGI send() calls."""
    # Build raw headers — pre-encoded content-type skips .encode() for common types
    raw_headers: list[tuple[bytes, bytes]] = [
        (b"content-type", _encode_content_type(response.content_type)),
    ]
    for name, value in response.headers:
        raw_headers.append((name.lower().encode("latin-1"), value.encode("latin-1")))
    raw_headers.extend(
        (b"set-cookie", cookie.to_header_value().encode("latin-1")) for cookie in response.cookies
    )
    if request_id is not None:
        raw_headers.append((b"x-request-id", request_id.encode("latin-1")))
    # Chirp DevTools tray + proxies: fragment vs full-page intent (HTML only)
    if response.content_type.startswith("text/html"):
        raw_headers.append((b"x-chirp-render-intent", response.render_intent.encode("latin-1")))

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
    request_id: str | None = None,
) -> None:
    """Send a streaming response via chunked transfer encoding.

    Sends headers immediately, then each chunk as an ASGI body
    message with ``more_body=True``. Closes with an empty body.
    On mid-stream error, emits an HTML comment and closes.
    """
    raw_headers: list[tuple[bytes, bytes]] = [
        (b"content-type", _encode_content_type(response.content_type)),
        (b"transfer-encoding", b"chunked"),
    ]
    for name, value in response.headers:
        raw_headers.append((name.lower().encode("latin-1"), value.encode("latin-1")))
    if request_id is not None:
        raw_headers.append((b"x-request-id", request_id.encode("latin-1")))

    # No content-length — chunked transfer encoding signals body boundaries
    await send(
        {
            "type": "http.response.start",
            "status": response.status,
            "headers": raw_headers,
        }
    )

    def _encode_chunk(chunk: str) -> bytes:
        return chunk.encode("utf-8")

    request_token: Token | None = None
    request_id_token: Token | None = None
    csp_nonce_token: Token | None = None
    if response.request_context is not None:
        request_token = request_var.set(response.request_context)
        request_id_token = request_id_var.set(response.request_context.request_id)
    if response.csp_nonce is not None:
        # Re-establish the CSP nonce while the generator drains. The middleware
        # finally already reset the var, so this is a self-contained set/reset
        # with its own token (no double-reset).
        from chirp.middleware.csp_nonce import _set_csp_nonce

        csp_nonce_token = _set_csp_nonce(response.csp_nonce)

    try:
        if isinstance(response.chunks, AsyncIterator):
            async for chunk in response.chunks:
                if chunk:
                    await send(
                        {
                            "type": "http.response.body",
                            "body": _encode_chunk(cast(str, chunk)),
                            "more_body": True,
                        }
                    )
        else:
            for chunk in response.chunks:
                if chunk:
                    await send(
                        {
                            "type": "http.response.body",
                            "body": _encode_chunk(cast(str, chunk)),
                            "more_body": True,
                        }
                    )
    except Exception as exc:
        # Mid-stream error: log with structured formatting, emit visible error
        import sys

        from chirp.server.terminal_errors import _is_kida_error, _plain_error_message, log_error

        log_error(exc)

        if debug:
            # Visible error div instead of invisible HTML comment
            import traceback

            error_msg = _plain_error_message(exc) if _is_kida_error(exc) else traceback.format_exc()
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
    finally:
        if request_token is not None:
            request_var.reset(request_token)
        if request_id_token is not None:
            request_id_var.reset(request_id_token)
        if csp_nonce_token is not None:
            from chirp.middleware.csp_nonce import _reset_csp_nonce

            _reset_csp_nonce(csp_nonce_token)

    # Close the stream
    await send(
        {
            "type": "http.response.body",
            "body": b"",
            "more_body": False,
        }
    )


def _format_http_date(timestamp: float) -> str:
    """Format a POSIX timestamp as an RFC 7231 IMF-fixdate string."""
    from email.utils import formatdate

    return formatdate(timestamp, usegmt=True)


def _parse_http_date(value: str) -> float | None:
    """Parse an HTTP-date header into a POSIX timestamp, or None if invalid."""
    from email.utils import parsedate_to_datetime

    try:
        return parsedate_to_datetime(value).timestamp()
    except TypeError, ValueError, IndexError, OverflowError:
        return None


def _etag_matches(if_none_match: str, etag: str) -> bool:
    """Return True if *etag* is matched by an ``If-None-Match`` header value.

    Handles the ``*`` wildcard and a comma-separated list of (possibly weak)
    entity-tags. Weak comparison is used for ``If-None-Match`` per RFC 9110.
    """
    if_none_match = if_none_match.strip()
    if if_none_match == "*":
        return True
    bare = etag[2:] if etag.startswith("W/") else etag
    for candidate in if_none_match.split(","):
        candidate = candidate.strip()
        cand_bare = candidate[2:] if candidate.startswith("W/") else candidate
        if cand_bare == bare:
            return True
    return False


def _parse_single_range(range_header: str, size: int) -> tuple[int, int] | None | bool:
    """Parse a single ``bytes=`` Range spec.

    Returns:
        ``(start, end)`` inclusive byte offsets for a satisfiable single range,
        ``False`` for an unsatisfiable range (caller should emit 416),
        ``None`` to ignore the header (multi-range / malformed -> fall back to 200).
    """
    range_header = range_header.strip()
    if not range_header.startswith("bytes="):
        return None
    spec = range_header[len("bytes=") :].strip()
    # Multi-range is not supported — fall back to a full 200 response.
    if "," in spec:
        return None
    if "-" not in spec:
        return None
    start_s, _, end_s = spec.partition("-")
    start_s = start_s.strip()
    end_s = end_s.strip()
    if start_s == "":
        # Suffix range: last N bytes.
        if end_s == "":
            return None
        try:
            suffix = int(end_s)
        except ValueError:
            return None
        if suffix <= 0:
            return False
        if suffix >= size:
            start, end = 0, size - 1
        else:
            start, end = size - suffix, size - 1
    else:
        try:
            start = int(start_s)
        except ValueError:
            return None
        if end_s == "":
            end = size - 1
        else:
            try:
                end = int(end_s)
            except ValueError:
                return None
            if end >= size:
                end = size - 1
        if start >= size:
            return False
        if start > end:
            return None
    if size == 0:
        return False
    return (start, end)


async def send_file_response(
    response: FileResponse,
    send: Send,
    *,
    request: Any = None,
    is_head: bool = False,
    request_id: str | None = None,
) -> None:
    """Send a :class:`FileResponse` from disk with conditional-GET / Range support.

    Streams the body in ``chunk_size`` reads off the event loop via
    :func:`anyio.to_thread.run_sync` (matching the data/cache to_thread precedent).
    Files smaller than ``stream_threshold`` are read in a single shot to keep
    small-file latency unchanged; larger files stream chunk-by-chunk so worker
    RSS stays bounded.

    Honours ``If-None-Match`` (weak compare, takes precedence) and
    ``If-Modified-Since`` -> 304, and a single byte ``Range`` -> 206 (416 when
    unsatisfiable) when ``response.conditional`` is True.

    On mid-stream IO error the stream is closed without an HTML error body — you
    cannot inject markup into a half-sent binary payload.
    """
    import os

    import anyio.to_thread

    path = response.path
    try:
        st = await anyio.to_thread.run_sync(os.stat, path)
    except OSError:
        logger.exception("send_file_response: stat failed for %s", path)
        await send(
            {
                "type": "http.response.start",
                "status": 500,
                "headers": [
                    (b"content-type", b"text/plain; charset=utf-8"),
                    (b"content-length", b"0"),
                ],
            }
        )
        await send({"type": "http.response.body", "body": b""})
        return

    size = st.st_size
    etag = f'"{size:x}-{st.st_mtime_ns:x}"'
    last_modified = _format_http_date(st.st_mtime)
    content_type = response.resolved_content_type

    # -- Common headers --
    def _base_headers() -> list[tuple[bytes, bytes]]:
        raw: list[tuple[bytes, bytes]] = [
            (b"content-type", _encode_content_type(content_type)),
        ]
        # Cache-Control is emitted once by the caller via
        # _cache_control_or_default; drop any author-supplied one to avoid a
        # duplicate header.
        for name, value in response.headers:
            if name.lower() == "cache-control":
                continue
            raw.append((name.lower().encode("latin-1"), value.encode("latin-1")))
        raw.extend(
            (b"set-cookie", cookie.to_header_value().encode("latin-1"))
            for cookie in response.cookies
        )
        if request_id is not None:
            raw.append((b"x-request-id", request_id.encode("latin-1")))
        return raw

    # -- Conditional GET (304) --
    status = response.status
    if response.conditional and status == 200 and request is not None:
        headers = request.headers
        inm = headers.get("if-none-match")
        ims = headers.get("if-modified-since")
        not_modified = False
        if inm is not None:
            # If-None-Match takes precedence over If-Modified-Since (RFC 9110).
            not_modified = _etag_matches(inm, etag)
        elif ims is not None:
            ims_ts = _parse_http_date(ims)
            # HTTP-date has whole-second resolution; truncate mtime so a file
            # last modified at e.g. 12:00:00.53 still matches a 12:00:00 header.
            if ims_ts is not None and int(st.st_mtime) <= int(ims_ts):
                not_modified = True
        if not_modified:
            raw = _base_headers()
            raw.append((b"etag", etag.encode("latin-1")))
            raw.append((b"last-modified", last_modified.encode("latin-1")))
            raw.append((b"cache-control", _cache_control_or_default(response)))
            raw.append((b"content-length", b"0"))
            await send({"type": "http.response.start", "status": 304, "headers": raw})
            await send({"type": "http.response.body", "body": b""})
            return

    # -- Range (206 / 416) --
    start = 0
    end = size - 1
    is_partial = False
    if response.conditional and status == 200 and request is not None:
        range_header = request.headers.get("range")
        if range_header is not None:
            parsed = _parse_single_range(range_header, size)
            if parsed is False:
                raw = _base_headers()
                raw.append((b"content-range", f"bytes */{size}".encode("latin-1")))
                raw.append((b"content-length", b"0"))
                await send({"type": "http.response.start", "status": 416, "headers": raw})
                await send({"type": "http.response.body", "body": b""})
                return
            if isinstance(parsed, tuple):
                start, end = parsed
                is_partial = True

    length = end - start + 1
    raw = _base_headers()
    raw.append((b"etag", etag.encode("latin-1")))
    raw.append((b"last-modified", last_modified.encode("latin-1")))
    raw.append((b"accept-ranges", b"bytes"))
    raw.append((b"cache-control", _cache_control_or_default(response)))
    raw.append((b"content-length", str(length).encode("latin-1")))
    if is_partial:
        raw.append((b"content-range", f"bytes {start}-{end}/{size}".encode("latin-1")))
        status = 206

    await send({"type": "http.response.start", "status": status, "headers": raw})

    if is_head or length == 0:
        await send({"type": "http.response.body", "body": b""})
        return

    # -- Stream body in chunks off the event loop --
    chunk_size = response.chunk_size
    try:

        def _open():
            return open(path, "rb")

        fh = await anyio.to_thread.run_sync(_open)
        try:
            await anyio.to_thread.run_sync(fh.seek, start)
            remaining = length
            # TOCTOU window: Content-Length was committed from the stat-time
            # ``size``, but the file may be truncated between stat and read.
            # If a read comes up short we have already promised more bytes in
            # the header, so we cannot recover the response — detect the
            # under-send, log it, and stop emitting body. ``remaining`` is the
            # shortfall checked after the loop.
            # Single-shot for small files; chunked loop at/above the threshold.
            if size < response.stream_threshold:
                data = await anyio.to_thread.run_sync(fh.read, remaining)
                remaining -= len(data)
                await send({"type": "http.response.body", "body": data, "more_body": True})
            else:
                while remaining > 0:
                    to_read = min(chunk_size, remaining)
                    data = await anyio.to_thread.run_sync(fh.read, to_read)
                    if not data:
                        break
                    remaining -= len(data)
                    await send(
                        {
                            "type": "http.response.body",
                            "body": data,
                            "more_body": True,
                        }
                    )
            if remaining > 0:
                # File shrank under us (truncated between stat and read). We
                # have sent fewer bytes than the promised Content-Length;
                # ASGI servers may error or hang waiting for the rest. Nothing
                # left to do but log loudly — the header is already on the wire.
                logger.error(
                    "send_file_response: short read for %s — %d of %d bytes "
                    "missing (file truncated after stat?); response under-sent",
                    path,
                    remaining,
                    length,
                )
        finally:
            await anyio.to_thread.run_sync(fh.close)
    except OSError:
        # Binary-safe error path: no HTML error div into a half-sent payload.
        logger.exception("send_file_response: read failed for %s", path)
    await send({"type": "http.response.body", "body": b"", "more_body": False})


def _cache_control_or_default(response: FileResponse) -> bytes:
    """Cache-Control header value, defaulting when not set on the response."""
    cc = response.header("Cache-Control")
    return (cc or "public, max-age=3600").encode("latin-1")
