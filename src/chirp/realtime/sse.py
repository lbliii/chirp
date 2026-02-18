"""Server-Sent Events protocol implementation over ASGI.

Handles the full SSE lifecycle: sends ``text/event-stream`` headers,
produces events from an async generator, monitors for client disconnect,
and sends periodic heartbeat comments to keep the connection alive.
"""

import asyncio
import contextlib
import json as json_module
import logging
from typing import Any

from kida import Environment

from chirp._internal.asgi import Receive, Send
from chirp.realtime.events import EventStream, SSEEvent
from chirp.templating.returns import Fragment

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
) -> None:
    """Stream Server-Sent Events over an ASGI connection.

    1. Sends ``http.response.start`` with ``text/event-stream`` headers.
    2. Launches two concurrent tasks:
       - **Event producer**: consumes the async generator, converts each
         yielded value to SSE wire format, and sends as ASGI body chunks.
       - **Disconnect monitor**: awaits ``http.disconnect`` from the client
         and cancels the producer.
    3. Sends periodic heartbeat comments (``:``) on idle.
    """
    # Send SSE headers
    await send(
        {
            "type": "http.response.start",
            "status": 200,
            "headers": [
                (b"content-type", b"text/event-stream"),
                (b"cache-control", b"no-cache"),
                (b"connection", b"keep-alive"),
                (b"x-accel-buffering", b"no"),
                (b"access-control-allow-origin", b"*"),
            ],
        }
    )

    if retry_ms is not None:
        retry_event = SSEEvent(data="sse-retry", event="chirp:sse:meta", retry=retry_ms)
        await send(
            {
                "type": "http.response.body",
                "body": retry_event.encode().encode("utf-8"),
                "more_body": True,
            }
        )

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
                    except RuntimeError:
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
                except Exception as render_exc:
                    from chirp.server.terminal_errors import log_error

                    log_error(render_exc)
                    if debug:
                        sse_text = _format_error_event(value, render_exc)
                    else:
                        continue  # Skip this event, keep stream alive

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
                        break  # Response already closed (client disconnected)
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            # Log with structured formatting for kida errors
            from chirp.server.terminal_errors import _is_kida_error, log_error

            log_error(exc)

            # Send an error event so the client can react
            if debug:
                if _is_kida_error(exc):
                    detail = (lambda e: getattr(e, "format_compact", lambda: str(e))())(exc)
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

    # Run producer and disconnect monitor concurrently
    producer_task = asyncio.create_task(produce_events())
    monitor_task = asyncio.create_task(monitor_disconnect())

    try:
        # Wait for either the producer to finish or disconnect
        _done, pending = await asyncio.wait(
            {producer_task, monitor_task},
            return_when=asyncio.FIRST_COMPLETED,
        )
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
        # Close the stream
        await send(
            {
                "type": "http.response.body",
                "body": b"",
                "more_body": False,
            }
        )


def _format_event(
    value: Any,
    *,
    default_event: str | None = None,
    kida_env: Environment | None = None,
) -> str:
    """Convert a yielded value to SSE wire format.

    Dispatch:
        - ``SSEEvent`` -> encode as-is
        - ``Fragment`` -> render via kida, wrap with event: fragment
        - ``str`` -> wrap as data
        - ``dict`` -> JSON-serialize as data
    """
    if isinstance(value, SSEEvent):
        return value.encode()

    if isinstance(value, Fragment):
        if kida_env is None:
            raise RuntimeError("Fragment events require kida integration.")
        from chirp.templating.integration import render_fragment

        html = render_fragment(kida_env, value)
        # Use the Fragment's target as the SSE event name when specified.
        # This allows sse-swap="target_id" on DOM elements to receive
        # updates for specific blocks (reactive templates pattern).
        event_name = value.target or "fragment"
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


def _format_error_event(value: Any, exc: Exception) -> str:
    """Format an error as an SSE event for a failed render.

    For ``Fragment`` values, uses the fragment's target as the SSE event
    name so the error replaces the specific block in the DOM.  This lets
    the developer see exactly which block broke, inline where it should be.

    For other value types, sends a generic ``error`` event.
    """
    from html import escape

    from chirp.server.terminal_errors import _is_kida_error

    if _is_kida_error(exc):
        detail = (lambda e: getattr(e, "format_compact", lambda: str(e))())(exc)
    else:
        detail = f"{type(exc).__name__}: {exc}"

    if isinstance(value, Fragment) and value.target:
        html = (
            f'<div class="chirp-block-error" data-block="{escape(value.block_name)}">'
            f"<strong>{escape(type(exc).__name__)}</strong>: {escape(str(exc))}"
            f"</div>"
        )
        return SSEEvent(data=html, event=value.target).encode()

    return SSEEvent(data=detail, event="error").encode()
