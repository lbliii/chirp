"""LLM Playground — compare 2 models side-by-side with streaming.

Requires: pip install chirp[ai] chirp-ui
Run: ollama serve && python app.py
"""

import os
from pathlib import Path
from urllib.parse import quote

import httpx

from chirp import App, AppConfig, EventStream, Fragment, Request, SSEEvent, Template, use_chirp_ui
from chirp.ai import LLM
from chirp.ai.streaming import stream_to_fragments
from chirp.markdown import register_markdown_filter
from chirp.middleware.static import StaticFiles

TEMPLATES_DIR = Path(__file__).parent / "templates"
PLAYGROUND_STATIC = Path(__file__).parent / "static" / "playground"

app = App(AppConfig(template_dir=TEMPLATES_DIR, debug=True, delegation=True))
app.add_middleware(StaticFiles(directory=str(PLAYGROUND_STATIC), prefix="/static/playground"))
use_chirp_ui(app)
register_markdown_filter(app)

OLLAMA_BASE = os.environ.get("OLLAMA_BASE", "http://localhost:11434")
DEFAULT_MODEL = os.environ.get("CHIRP_LLM", "ollama:llama3.2").replace("ollama:", "")


async def _ollama_models() -> list[str]:
    try:
        async with httpx.AsyncClient(base_url=OLLAMA_BASE, timeout=5.0) as client:
            resp = await client.get("/api/tags")
            resp.raise_for_status()
            return [m["name"] for m in resp.json().get("models", [])]
    except Exception:
        return []


@app.route("/", template="index.html")
async def index() -> Template:
    models = await _ollama_models()
    default = DEFAULT_MODEL if DEFAULT_MODEL in models else (models[0] if models else "llama3.2")
    # model_b defaults to second model if available (avoid same as model_a)
    default_b = models[1] if len(models) > 1 else default
    return Template(
        "index.html",
        models=models,
        default_model=default,
        default_model_b=default_b,
    )


@app.route("/ask", methods=["POST"], template="playground.html")
async def ask(request: Request):
    form = await request.form()
    prompt = (form.get("prompt") or "").strip()
    if not prompt:
        return Fragment("playground.html", "empty")

    model_a = (form.get("model_a") or "").strip() or DEFAULT_MODEL
    model_b = (form.get("model_b") or "").strip() or DEFAULT_MODEL

    url_a = f"/ask/stream?prompt={quote(prompt)}&model={quote(model_a)}"
    url_b = f"/ask/stream?prompt={quote(prompt)}&model={quote(model_b)}"

    return Fragment(
        "playground.html",
        "compare_result",
        prompt=prompt,
        model_a=model_a,
        model_b=model_b,
        stream_url_a=url_a,
        stream_url_b=url_b,
    )


@app.route("/ask/stream", referenced=True, template="playground.html")
async def ask_stream(request: Request) -> EventStream:
    prompt = (request.query.get("prompt") or "").strip()
    model_name = (request.query.get("model") or "").strip() or DEFAULT_MODEL

    async def generate():
        if not prompt:
            yield Fragment("playground.html", "response", text="No prompt provided.")
            yield SSEEvent(event="done", data="complete")
            return

        llm = LLM(f"ollama:{model_name}")
        fragments = stream_to_fragments(
            llm.stream(prompt),
            "playground.html",
            "response",
            context_key="text",
        )
        async for frag in fragments:
            yield frag
        yield SSEEvent(event="done", data="complete")

    return EventStream(generate())


if __name__ == "__main__":
    app.run()
