"""LLM Minimal — the smallest streaming-LLM example (no Ollama required).

The 5-minute path between the ChirpUI ``llm_playground`` and the heavier
``ollama`` example. Streams tokens to the browser two ways so you can feel
the difference:

- ``/ask``    — ``TemplateStream`` + ``{% async for %}``: full-page chunked HTML.
- ``/stream`` — ``EventStream`` + ``Fragment``-per-token: SSE after form submit.

Simulated tokens by default — no Ollama, no API keys. Set ``USE_OLLAMA=1``
(with ``ollama serve``) to stream from a real local LLM via ``chirp.ai.LLM``.

Run:
    PYTHONPATH=src python examples/standalone/llm_minimal/app.py
"""

import asyncio
import os
from collections.abc import AsyncIterator
from pathlib import Path
from urllib.parse import quote

from chirp import (
    App,
    AppConfig,
    EventStream,
    Fragment,
    Request,
    SSEEvent,
    Template,
    TemplateStream,
)

TEMPLATES_DIR = Path(__file__).parent / "templates"

config = AppConfig(template_dir=TEMPLATES_DIR, worker_mode="async", sse_close_event="close")
app = App(config=config)

USE_OLLAMA = os.environ.get("USE_OLLAMA", "0") in ("1", "true", "yes")
# Fast tokens in tests/CI; a visible typing cadence when run by hand.
TOKEN_DELAY = float(os.environ.get("LLM_MINIMAL_DELAY", "0.04"))


async def simulated_stream(prompt: str) -> AsyncIterator[str]:
    """Fake LLM tokens. In production this is ``llm.stream(prompt)``."""
    reply = (
        f"You asked: {prompt}\n\n"
        "Tokens are typed out in the browser — still just Python, "
        "no frontend build. Swap simulated_stream for a real model "
        "and the rest of the example stays the same."
    )
    for word in reply.split(" "):
        await asyncio.sleep(TOKEN_DELAY)
        yield word + " "


async def get_stream(prompt: str) -> AsyncIterator[str]:
    """Real token stream when USE_OLLAMA=1, otherwise the simulated one.

    Falls back to the simulated stream if Ollama is unreachable, so the
    example never hard-fails just because a local model is not running.
    """
    if USE_OLLAMA:
        live = _ollama_stream(prompt)
        if live is not None:
            async for token in live:
                yield token
            return
    async for token in simulated_stream(prompt):
        yield token


def _ollama_stream(prompt: str) -> AsyncIterator[str] | None:
    try:
        from chirp.ai import LLM  # optional: pip install chirp[ai]

        return LLM("ollama:llama3.2").stream(prompt)
    except Exception:
        return None


@app.route("/")
async def index() -> Template:
    """Render the prompt form."""
    return Template("index.html")


@app.route("/ask", methods=["POST"])
async def ask(request: Request) -> TemplateStream:
    """TemplateStream — full-page chunked HTML driven by ``{% async for %}``."""
    form = await request.form()
    prompt = (form.get("prompt") or "").strip() or "What is Chirp?"
    return TemplateStream(
        "response.html",
        prompt=prompt,
        stream=get_stream(prompt),
    )


@app.route("/stream/start", methods=["POST"])
async def stream_start(request: Request) -> Fragment:
    """Return an SSE panel wired to ``/stream`` with the submitted prompt."""
    form = await request.form()
    prompt = (form.get("prompt") or "").strip() or "What is Chirp?"
    stream_url = f"/stream?prompt={quote(prompt)}"
    return Fragment("sse_panel.html", "sse_panel", prompt=prompt, stream_url=stream_url)


@app.route("/stream", referenced=True)
async def stream(request: Request) -> EventStream:
    """EventStream — one SSE Fragment per token, swapped in by htmx."""

    prompt = (request.query.get("prompt") or "").strip() or "What is Chirp?"

    async def generate() -> AsyncIterator[Fragment | SSEEvent]:
        async for token in get_stream(prompt):
            yield Fragment("response.html", "token", token=token)
        yield SSEEvent(event="close", data="done")

    return EventStream(generate())


if __name__ == "__main__":
    app.run()
