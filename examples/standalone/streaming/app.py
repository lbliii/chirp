"""Streaming — Stream() and TemplateStream() with visible chunk delivery.

- / — Stream() with awaitables (resolves concurrently, then chunks stream out)
- /live — TemplateStream() with slow async iterator (watch chunks arrive every 2s)

Run:
    python app.py
"""

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path

from chirp import App, AppConfig, Stream, TemplateStream

TEMPLATES_DIR = Path(__file__).parent / "templates"

config = AppConfig(template_dir=TEMPLATES_DIR, worker_mode="async")
app = App(config=config)


async def load_stats() -> list[dict[str, str | int]]:
    """Simulate slow stats fetch (e.g. database aggregate)."""
    await asyncio.sleep(0.5)
    return [
        {"label": "Users", "value": 1247},
        {"label": "Orders", "value": 89},
        {"label": "Revenue", "value": 12400},
    ]


async def load_feed() -> list[dict[str, str]]:
    """Simulate slower feed fetch (e.g. external API)."""
    await asyncio.sleep(1.0)
    return [
        {"title": "New order #1001", "time": "2 min ago"},
        {"title": "User signup", "time": "5 min ago"},
        {"title": "Payment received", "time": "12 min ago"},
    ]


@app.route("/")
async def index():
    """Stream the page — stats and feed resolve concurrently, then chunks stream out."""
    return Stream(
        "dashboard.html",
        stats=load_stats(),
        feed=load_feed(),
    )


def _live_delay() -> float:
    """2s for demo; 0.05s when STREAMING_FAST=1 (tests)."""
    import os

    return 0.05 if os.environ.get("STREAMING_FAST") else 2.0


async def _live_items() -> AsyncIterator[dict[str, str]]:
    """Yield items every few seconds — visible chunk delivery."""
    items = [
        {"title": "First item", "time": "now"},
        {"title": "Second item", "time": "+2s"},
        {"title": "Third item", "time": "+4s"},
        {"title": "Fourth item", "time": "+6s"},
        {"title": "Done", "time": "+8s"},
    ]
    delay = _live_delay()
    for item in items:
        await asyncio.sleep(delay)
        yield item


@app.route("/live")
async def live():
    """TemplateStream — watch chunks arrive every 2 seconds."""
    return TemplateStream("live.html", stream=_live_items())


if __name__ == "__main__":
    app.run()
