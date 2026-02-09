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
    await send({
        "type": "http.response.start",
        "status": 200,
        "headers": [
            (b"content-type", b"text/event-stream"),
            (b"cache-control", b"no-cache"),
            (b"connection", b"keep-alive"),
        ],
    })

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

        Wraps each ``__anext__()`` in ``asyncio.shield`` + ``wait_for``
        so that heartbeat comments are sent when the generator is idle
        longer than ``heartbeat_interval``, without cancelling the
        pending ``__anext__()`` coroutine.
        """
        pending_next: asyncio.Task[Any] | None = None
        try:
            heartbeat_interval = event_stream.heartbeat_interval
            gen_iter = event_stream.generator.__aiter__()

            while not disconnected.is_set():
                # Get or create the task for the next value
                if pending_next is None:
                    pending_next = asyncio.create_task(gen_iter.__anext__())

                # Wait for it with a heartbeat timeout.
                # asyncio.shield prevents wait_for from cancelling the
                # underlying task on timeout — the __anext__() call
                # survives across heartbeat intervals.
                try:
                    value = await asyncio.wait_for(
                        asyncio.shield(pending_next),
                        timeout=heartbeat_interval,
                    )
                    pending_next = None  # consumed — create fresh next time
                except TimeoutError:
                    # Generator is idle — send heartbeat, keep waiting
                    if disconnected.is_set():
                        break
                    await send({
                        "type": "http.response.body",
                        "body": b": heartbeat\n\n",
                        "more_body": True,
                    })
                    continue
                except StopAsyncIteration:
                    pending_next = None
                    break

                sse_text = _format_event(
                    value,
                    default_event=event_stream.event_type,
                    kida_env=kida_env,
                )
                if sse_text:
                    await send({
                        "type": "http.response.body",
                        "body": sse_text.encode("utf-8"),
                        "more_body": True,
                    })
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            logger.exception("SSE event generator error")
            # Send an error event so the client can react
            if debug:
                import traceback

                detail = traceback.format_exc()
            else:
                detail = "Internal server error"
            error_event = SSEEvent(data=detail, event="error")
            with contextlib.suppress(Exception):
                await send({
                    "type": "http.response.body",
                    "body": error_event.encode().encode("utf-8"),
                    "more_body": True,
                })
        finally:
            # Always clean up pending __anext__ task — whether we exited
            # normally, via CancelledError (disconnect), or via exception.
            # Without this, a completed task's StopAsyncIteration goes
            # unretrieved and Python logs a noisy warning.
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
        # Close the stream
        await send({
            "type": "http.response.body",
            "body": b"",
            "more_body": False,
        })


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
        event = SSEEvent(data=html, event="fragment")
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
