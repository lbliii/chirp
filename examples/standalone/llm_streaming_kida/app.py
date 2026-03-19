"""LLM Streaming with Kida — TemplateStream + {% async for %}.

Demonstrates TemplateStream: a template with {% async for token in stream %}
consumes an async iterator and yields chunks as it iterates. O(n) work —
one template render, not Fragment-per-token re-renders.

Uses a simulated stream by default (no Ollama required). Set USE_OLLAMA=1
and run `ollama serve` to use a real LLM.

Run:
    python app.py
"""

import asyncio
import os
from collections.abc import AsyncIterator
from pathlib import Path

from chirp import App, AppConfig, Request, Template, TemplateStream

TEMPLATES_DIR = Path(__file__).parent / "templates"

config = AppConfig(template_dir=TEMPLATES_DIR)
app = App(config=config)

USE_OLLAMA = os.environ.get("USE_OLLAMA", "0") in ("1", "true", "yes")


async def simulated_stream(prompt: str) -> AsyncIterator[str]:
    """Simulate LLM tokens. In production: llm.stream(prompt)."""
    tokens = [
        "Kida",
        " is",
        " a",
        " modern",
        " template",
        " engine",
        " with",
        " ",
        "{% async for %}",
        " —",
        " it",
        " streams",
        " as",
        " it",
        " iterates.",
    ]
    for token in tokens:
        await asyncio.sleep(0.03)
        yield token


async def get_stream(prompt: str) -> AsyncIterator[str]:
    """Return real or simulated token stream."""
    if USE_OLLAMA:
        try:
            from chirp.ai import LLM

            llm = LLM("ollama:llama3.2")
            async for token in llm.stream(prompt):
                yield token
        except Exception:
            async for token in simulated_stream(prompt):
                yield token
    else:
        async for token in simulated_stream(prompt):
            yield token


@app.route("/")
async def index() -> Template:
    """Render the form."""
    return Template("index.html")


@app.route("/ask", methods=["POST"])
async def ask(request: Request) -> TemplateStream:
    """Stream the response via Kida's {% async for %} — O(n) template render."""
    form = await request.form()
    prompt = (form.get("prompt") or "").strip() or "What is Kida?"
    return TemplateStream(
        "response.html",
        prompt=prompt,
        stream=get_stream(prompt),
    )


if __name__ == "__main__":
    app.run()
