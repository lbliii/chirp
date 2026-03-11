"""Chirp mixed workload benchmark — JSON + SSE in same app.

Verifies adaptive dispatch: /json uses sync path, /stream hands off to async pool.
"""

import asyncio
import os

from chirp import App, AppConfig, EventStream, SSEResponse

worker_mode = os.environ.get("CHIRP_WORKER_MODE", "auto")
app = App(
    AppConfig(
        debug=False,
        workers=10,
        request_queue_enabled=False,
        worker_mode=worker_mode,
    )
)

JSON_PAYLOAD = {"message": "hello", "count": 42}


async def _stream_tokens(count: int = 5, delay: float = 0.05):
    """Simulate token streaming (e.g. LLM response)."""
    for i in range(count):
        await asyncio.sleep(delay)
        yield {"token": f"chunk-{i}", "index": i}


@app.route("/json")
async def json_handler():
    return JSON_PAYLOAD


@app.route("/stream")
async def stream_handler():
    """SSE stream — should hand off to async pool when worker_mode=sync."""
    stream = EventStream(_stream_tokens(), heartbeat_interval=30.0)
    return SSEResponse(event_stream=stream)
