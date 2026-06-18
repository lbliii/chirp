"""Server-Sent Events protocol implementation over ASGI.

Handles the full SSE lifecycle: sends ``text/event-stream`` headers,
produces events from an async generator, monitors for client disconnect,
and sends periodic heartbeat comments to keep the connection alive.
"""

import asyncio
import contextlib
import json as json_module
import logging
from collections.abc import Callable
from contextvars import Token
from typing import TYPE_CHECKING, Any

from kida import Environment

from chirp._internal.asgi import Receive, Send
from chirp.realtime.events import EventStream, SSEEvent
from chirp.templating.returns import Fragment

if TYPE_CHECKING:
    from chirp.server.streaming_context import _CapturedRequestContext

logger = logging.getLogger("chirp.server")


async def handle_sse(
    event_stream: EventStream,
    send: Send,
    receive: Receive,
    *,
    kida_env: Environment | None = None,
    debug: bool = False,
    retry_ms: int | None = None,
    close_event: str | None = None,
    allow_origin: str | None = None,
    trace_sink: Callable[[str, dict[str, Any]], None] | None = None,
    extra_headers: tuple[tuple[bytes, bytes], ...] = (),
    captured_context: _CapturedRequestContext | None = None,
) -> None:
    """Stream Server-Sent Events over an ASGI connection.

    1. Sends ``http.response.start`` with ``text/event-stream`` headers.
    2. Launches two concurrent tasks:
       - **Event producer**: consumes the async generator, converts each
         yielded value to SSE wire format, and sends as ASGI body chunks.
       - **Disconnect monitor**: awaits ``http.disconnect`` from the client
         and cancels the producer.
    3. Sends periodic heartbeat comments (``:``) on idle.

    *captured_context* carries the request-scoped state (request, auth user,
    CSRF token, ``g``, CSP nonce) snapshotted at negotiation time, while the
    middleware ContextVars were still live. The handler ``finally`` resets
    those vars the instant it returns — before any event is produced here — so
    they are re-established inside ``produce_events`` (in its own task) for the
    lifetime of the stream. This keeps ``get_request()``, ``get_user()`` /
    ``current_user()``, ``get_csrf_token()``, ``g``, and the live CSP nonce
    working identically inside the EventStream generator (mirrors the
    ``StreamingResponse`` drain in :func:`chirp.server.sender`).

    SSE identity is **pinned at connect time**: the captured snapshot is fixed
    for the connection's lifetime. A user logged out or permission-revoked
    mid-stream keeps the connect-time identity until they reconnect.
    """
    # Send SSE headers.
    #
    # SSE responses default to SAME-ORIGIN: no Access-Control-Allow-Origin
    # header is emitted unless the EventStream explicitly opts into a specific
    # cross-origin policy via allow_origin. handle_sse builds these headers
    # directly (app-level CORSMiddleware does not apply to the SSE byte stream),
    # so EventStream.allow_origin is the single, explicit knob. Previously this
    # always emitted a hardcoded `*` — an unconditional, insecure cross-origin
    # default with no way to scope it (see #146).
    sse_headers: list[tuple[bytes, bytes]] = [
        (b"content-type", b"text/event-stream"),
        (b"cache-control", b"no-cache"),
        (b"connection", b"keep-alive"),
        (b"x-accel-buffering", b"no"),
    ]
    if allow_origin is not None:
        sse_headers.append((b"access-control-allow-origin", allow_origin.encode("latin-1")))
        # Responses vary by Origin once CORS is in play, so caches must not
        # serve a cross-origin-allowed body to a different origin.
        sse_headers.append((b"vary", b"Origin"))
    sse_headers.extend(extra_headers)
    await send(
        {
            "type": "http.response.start",
            "status": 200,
            "headers": sse_headers,
        }
    )
    if trace_sink is not None:
        trace_sink("start", {"heartbeat_interval": event_stream.heartbeat_interval})

    if retry_ms is not None:
        retry_event = SSEEvent(data="sse-retry", event="chirp:sse:meta", retry=retry_ms)
        await send(
            {
                "type": "http.response.body",
                "body": retry_event.encode().encode("utf-8"),
                "more_body": True,
            }
        )
        if trace_sink is not None:
            trace_sink("retry", {"retry_ms": retry_ms})

    # Track disconnect
    disconnected = asyncio.Event()

    async def monitor_disconnect() -> None:
        """Wait for client disconnect."""
        while not disconnected.is_set():
            message = await receive()
            if message.get("type") == "http.disconnect":
                disconnected.set()
                return

    async def produce_events() -> None:
        """Consume generator and send SSE events.

        Uses ``asyncio.wait`` with a timeout to send heartbeat comments
        when the generator is idle.  The pending ``__anext__()`` task
        survives across heartbeat intervals because ``asyncio.wait``
        does not cancel tasks on timeout (unlike ``wait_for``).

        Previous implementation used ``wait_for(shield(pending_next))``
        which caused ``StopAsyncIteration exception in shielded future``
        noise: when the shield wrapper was cancelled on disconnect,
        ``asyncio.shield``'s ``_log_on_exception`` callback fired before
        the ``finally`` block could suppress the exception.
        """
        pending_next: asyncio.Task[Any] | None = None
        # Re-establish the captured request-scoped context for the whole stream
        # lifetime. The handler finally already reset these vars (it runs before
        # the SSE drain), so each is a self-contained set/reset with its own
        # token. produce_events runs in its own task, so setting here guarantees
        # the vars are live for every _format_event (render_fragment) call and
        # stable across the connection's lifetime.
        request_token: Token | None = None
        request_id_token: Token | None = None
        csp_nonce_token: Token | None = None
        auth_user_token: Token | None = None
        csrf_token_token: Token | None = None
        csrf_field_token: Token | None = None
        g_token: Token | None = None
        ctx = captured_context
        if ctx is not None:
            if ctx.request_context is not None:
                from chirp.context import request_var
                from chirp.logging import request_id_var

                request_token = request_var.set(ctx.request_context)
                request_id_token = request_id_var.set(ctx.request_context.request_id)
            if ctx.csp_nonce is not None:
                from chirp.middleware.csp_nonce import _set_csp_nonce

                csp_nonce_token = _set_csp_nonce(ctx.csp_nonce)
            if ctx.auth_user is not None:
                from chirp.middleware.auth import _set_stream_user

                auth_user_token = _set_stream_user(ctx.auth_user)
            if ctx.csrf_token is not None:
                from chirp.middleware.csrf import _set_stream_csrf

                csrf_token_token, csrf_field_token = _set_stream_csrf(
                    ctx.csrf_token,
                    ctx.csrf_field_name,
                )
            # Gate on `is not None` (not truthiness): an empty-dict snapshot must
            # still install a writable g store for the generator.
            if ctx.g_snapshot is not None:
                from chirp.context import g

                g_token = g._restore(ctx.g_snapshot)
        try:
            heartbeat_interval = event_stream.heartbeat_interval
            gen_iter = event_stream.generator.__aiter__()

            while not disconnected.is_set():
                # Get or create the task for the next value
                if pending_next is None:

                    async def _next() -> Any:
                        return await gen_iter.__anext__()

                    pending_next = asyncio.create_task(_next())

                # Wait with timeout — asyncio.wait does NOT cancel the
                # task on timeout, so __anext__() survives across
                # heartbeat intervals without needing asyncio.shield.
                done, _ = await asyncio.wait(
                    {pending_next},
                    timeout=heartbeat_interval,
                )

                if not done:
                    # Timeout: generator is idle — send heartbeat
                    if disconnected.is_set():
                        break
                    try:
                        await send(
                            {
                                "type": "http.response.body",
                                "body": b": heartbeat\n\n",
                                "more_body": True,
                            }
                        )
                        if trace_sink is not None:
                            trace_sink("heartbeat", {})
                    except RuntimeError:
                        if trace_sink is not None:
                            trace_sink("send_failed", {"during": "heartbeat"})
                        break  # Response already closed (client disconnected)
                    continue

                # Task completed — retrieve result
                pending_next = None
                try:
                    value = done.pop().result()
                except StopAsyncIteration:
                    break

                # Error boundary: per-event isolation.  A rendering failure
                # in one block should not kill the entire stream.
                try:
                    sse_text = _format_event(
                        value,
                        default_event=event_stream.event_type,
                        kida_env=kida_env,
                    )
                    if trace_sink is not None:
                        trace_sink("event", _trace_event_payload(value, sse_text))
                except Exception as render_exc:
                    from chirp.server.terminal_errors import log_error

                    log_error(render_exc)
                    if trace_sink is not None:
                        trace_sink(
                            "render_error",
                            {
                                "value_type": type(value).__name__,
                                "error_type": type(render_exc).__name__,
                                "message": str(render_exc),
                            },
                        )
                    # Always send an error event so clients know an event
                    # was lost.  In debug mode, include targeted block info;
                    # in production, send a generic error event.
                    if debug:
                        sse_text = _format_error_event(value, render_exc)
                    else:
                        sse_text = SSEEvent(
                            data="Event rendering failed",
                            event="error",
                        ).encode()

                if sse_text:
                    try:
                        await send(
                            {
                                "type": "http.response.body",
                                "body": sse_text.encode("utf-8"),
                                "more_body": True,
                            }
                        )
                    except RuntimeError:
                        if trace_sink is not None:
                            trace_sink("send_failed", {"during": "event"})
                        break  # Response already closed (client disconnected)
        except asyncio.CancelledError:
            if trace_sink is not None:
                trace_sink("cancelled", {})
        except Exception as exc:
            # Log with structured formatting for kida errors
            from chirp.server.terminal_errors import (
                _is_kida_error,
                _plain_error_message,
                is_client_disconnect,
                log_error,
            )

            if is_client_disconnect(exc):
                # The peer vanished mid-stream (TCP reset / broken pipe). Benign:
                # the socket is gone, so there is nothing to send and nothing to
                # alert on. Log at DEBUG and fall through to cleanup — do NOT emit
                # a 500-class "Server error" for a client that simply left.
                logger.debug("SSE client disconnected mid-stream: %r", exc)
                if trace_sink is not None:
                    trace_sink("client_disconnect", {"error_type": type(exc).__name__})
            else:
                log_error(exc)
                if trace_sink is not None:
                    trace_sink(
                        "generator_error",
                        {
                            "error_type": type(exc).__name__,
                            "message": str(exc),
                        },
                    )

                # Send an error event so the client can react
                if debug:
                    if _is_kida_error(exc):
                        detail = _plain_error_message(exc)
                    else:
                        import traceback

                        detail = traceback.format_exc()
                else:
                    detail = "Internal server error"
                error_event = SSEEvent(data=detail, event="error")
                with contextlib.suppress(Exception):
                    await send(
                        {
                            "type": "http.response.body",
                            "body": error_event.encode().encode("utf-8"),
                            "more_body": True,
                        }
                    )
        finally:
            # Always clean up pending __anext__ task — whether we exited
            # normally, via CancelledError (disconnect), or via exception.
            if pending_next is not None:
                if not pending_next.done():
                    pending_next.cancel()
                with contextlib.suppress(asyncio.CancelledError, StopAsyncIteration):
                    await pending_next
            # Close the generator so user try/finally blocks run
            # (e.g. database connection cleanup, file handle release).
            # AsyncIterator doesn't guarantee aclose(); AsyncGenerator does.
            _aclose = getattr(gen_iter, "aclose", None)
            if _aclose is not None:
                with contextlib.suppress(Exception):
                    await _aclose()
            # Reset the request-scoped vars last so they stay live through
            # generator aclose() (user try/finally blocks may render a final
            # Fragment that reads the request/user/CSRF/g). Each resets the same
            # var it set, so a later unrelated request never sees this stream's
            # identity or g — critical under free-threading (3.14t).
            if g_token is not None:
                from chirp.context import g

                g._restore_reset(g_token)
            if csrf_token_token is not None:
                from chirp.middleware.csrf import _reset_stream_csrf

                _reset_stream_csrf(csrf_token_token, csrf_field_token)
            if auth_user_token is not None:
                from chirp.middleware.auth import _reset_stream_user

                _reset_stream_user(auth_user_token)
            if csp_nonce_token is not None:
                from chirp.middleware.csp_nonce import _reset_csp_nonce

                _reset_csp_nonce(csp_nonce_token)
            if request_id_token is not None:
                from chirp.logging import request_id_var

                request_id_var.reset(request_id_token)
            if request_token is not None:
                from chirp.context import request_var

                request_var.reset(request_token)

    # Run producer and disconnect monitor concurrently
    producer_task = asyncio.create_task(produce_events())
    monitor_task = asyncio.create_task(monitor_disconnect())

    try:
        # Wait for either the producer to finish or disconnect
        _done, pending = await asyncio.wait(
            {producer_task, monitor_task},
            return_when=asyncio.FIRST_COMPLETED,
        )
        if trace_sink is not None and monitor_task.done() and not producer_task.done():
            trace_sink("disconnect", {})
        for task in pending:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
    finally:
        if close_event:
            with contextlib.suppress(Exception):
                close_payload = SSEEvent(data="complete", event=close_event).encode()
                await send(
                    {
                        "type": "http.response.body",
                        "body": close_payload.encode("utf-8"),
                        "more_body": True,
                    }
                )
                if trace_sink is not None:
                    trace_sink("close_event", {"event": close_event})
        # Close the stream
        await send(
            {
                "type": "http.response.body",
                "body": b"",
                "more_body": False,
            }
        )
        if trace_sink is not None:
            trace_sink("closed", {})


def _format_event(
    value: Any,
    *,
    default_event: str | None = None,
    kida_env: Environment | None = None,
) -> str:
    """Convert a yielded value to SSE wire format.

    Dispatch:
        - ``SSEEvent`` -> encode as-is
        - ``Fragment`` -> render via kida, using its target as event name when set
        - ``str`` -> wrap as data
        - ``dict`` -> JSON-serialize as data
    """
    if isinstance(value, SSEEvent):
        return value.encode()

    if isinstance(value, Fragment):
        if kida_env is None:
            raise RuntimeError("Fragment events require kida integration.")
        from chirp.templating.integration import render_fragment

        html = render_fragment(kida_env, value).strip()
        # Use the Fragment's target as the SSE event name when specified.
        # This allows sse-swap="target_id" on DOM elements to receive
        # updates for specific blocks (reactive templates pattern).
        # Note: no OOB wrapper — sse-swap matches on event name alone,
        # and OOB would replace the target element, destroying the
        # sse-swap attribute and breaking subsequent updates.
        event_name = value.target or default_event
        event = SSEEvent(data=html, event=event_name)
        return event.encode()

    if isinstance(value, str):
        event = SSEEvent(data=value, event=default_event)
        return event.encode()

    if isinstance(value, dict):
        event = SSEEvent(data=json_module.dumps(value, default=str), event=default_event)
        return event.encode()

    # Unknown type: convert to string
    event = SSEEvent(data=str(value), event=default_event)
    return event.encode()


def _trace_event_payload(value: Any, sse_text: str) -> dict[str, Any]:
    """Return bounded metadata about a formatted SSE event."""
    event_name = None
    event_id = None
    retry = None
    data_lines = 0
    for line in sse_text.splitlines():
        if line.startswith("event: "):
            event_name = line[7:]
        elif line.startswith("id: "):
            event_id = line[4:]
        elif line.startswith("retry: "):
            retry = line[7:]
        elif line.startswith("data: "):
            data_lines += 1
    return {
        "value_type": type(value).__name__,
        "event": event_name,
        "id": event_id,
        "retry": retry,
        "data_lines": data_lines,
    }


def _format_error_event(value: Any, exc: Exception) -> str:
    """Format an error as an SSE event for a failed render.

    For ``Fragment`` values, uses the fragment's target as the SSE event
    name so the error replaces the specific block in the DOM.  This lets
    the developer see exactly which block broke, inline where it should be.

    For other value types, sends a generic ``error`` event.
    """
    from html import escape

    from chirp.server.terminal_errors import _is_kida_error, _plain_error_message

    detail = _plain_error_message(exc) if _is_kida_error(exc) else f"{type(exc).__name__}: {exc}"

    if isinstance(value, Fragment) and value.target:
        plain_msg = _plain_error_message(exc)
        html = (
            f'<div class="chirp-block-error" data-block="{escape(value.block_name)}">'
            f"<strong>{escape(type(exc).__name__)}</strong>: {escape(plain_msg)}"
            f"</div>"
        )
        return SSEEvent(data=html, event=value.target).encode()

    return SSEEvent(data=detail, event="error").encode()
