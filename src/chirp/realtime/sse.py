"""Server-Sent Events protocol implementation over ASGI.

Handles the full SSE lifecycle: sends ``text/event-stream`` headers,
produces events from an async generator, monitors for client disconnect,
and sends periodic heartbeat comments to keep the connection alive.
"""

import asyncio
import json as json_module
from typing import Any

from kida import Environment

from chirp._internal.asgi import Receive, Send
from chirp.realtime.events import EventStream, SSEEvent
from chirp.templating.returns import Fragment


async def handle_sse(
    event_stream: EventStream,
    send: Send,
    receive: Receive,
    *,
    kida_env: Environment | None = None,
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
        """Consume generator and send SSE events."""
        try:
            heartbeat_interval = event_stream.heartbeat_interval

            async def next_event_with_heartbeat():
                """Get next event, sending heartbeats on idle."""
                gen = event_stream.generator.__aiter__()
                while True:
                    try:
                        value = await asyncio.wait_for(
                            gen.__anext__(),
                            timeout=heartbeat_interval,
                        )
                        return value
                    except TimeoutError:
                        # Send heartbeat comment
                        if disconnected.is_set():
                            return None
                        await send({
                            "type": "http.response.body",
                            "body": b": heartbeat\n\n",
                            "more_body": True,
                        })

            async for value in event_stream.generator:
                if disconnected.is_set():
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

    # Run producer and disconnect monitor concurrently
    producer_task = asyncio.create_task(produce_events())
    monitor_task = asyncio.create_task(monitor_disconnect())

    try:
        # Wait for either the producer to finish or disconnect
        done, pending = await asyncio.wait(
            {producer_task, monitor_task},
            return_when=asyncio.FIRST_COMPLETED,
        )
        for task in pending:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
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
