"""Streaming answer scaffold for ``chirp new --stream``.

Teaches TemplateStream (plain POST, full page) and EventStream (Fragment +
parametric SSE) side by side — the safe transport x client pairings from
``examples/standalone/llm_minimal/``.
"""

STREAM_APP_PY = """\
\"\"\"{name} — simulated token streaming (TemplateStream + EventStream).\"\"\"

import asyncio
import os

from project_paths import ROOT
from collections.abc import AsyncIterator
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
    secure_stack,
)

TEMPLATES_DIR = ROOT / "templates"
app = App(
    AppConfig.from_env(
        csp_nonce_enabled=True,
        template_dir=TEMPLATES_DIR,
        worker_mode="async",
        sse_close_event="close",
    )
)
for middleware in secure_stack(app.config):
    app.add_middleware(middleware)

TOKEN_DELAY = float(os.environ.get("STREAM_DELAY", "0.04"))


async def simulated_stream(prompt: str) -> AsyncIterator[str]:
    reply = (
        f"You asked: {{prompt}}\\n\\n"
        "Tokens stream to the browser — still just Python, no frontend build."
    )
    for word in reply.split(" "):
        await asyncio.sleep(TOKEN_DELAY)
        yield word + " "


@app.route("/")
async def index() -> Template:
    return Template("index.html", title="{name}")


@app.route("/ask", methods=["POST"])
async def ask(request: Request) -> TemplateStream:
    form = await request.form()
    prompt = (form.get("prompt") or "").strip() or "Hello"
    return TemplateStream("response.html", prompt=prompt, stream=simulated_stream(prompt))


@app.route("/stream/start", methods=["POST"])
async def stream_start(request: Request) -> Fragment:
    form = await request.form()
    prompt = (form.get("prompt") or "").strip() or "Hello"
    stream_url = f"/stream?prompt={{quote(prompt)}}"
    return Fragment("sse_panel.html", "sse_panel", prompt=prompt, stream_url=stream_url)


@app.route("/stream", referenced=True)
async def stream(request: Request) -> EventStream:
    prompt = (request.query.get("prompt") or "").strip() or "Hello"

    async def generate():
        async for token in simulated_stream(prompt):
            yield Fragment("response.html", "token", text_chunk=token)
        yield SSEEvent(event="close", data="done")

    return EventStream(generate())


if __name__ == "__main__":
    app.run()
"""

STREAM_INDEX_HTML = """\
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>{{ title }} — streaming</title>
  <script src="https://cdn.jsdelivr.net/npm/htmx.org@2.0.10/dist/htmx.min.js"></script>
  <script src="https://unpkg.com/htmx-ext-sse@2.2.2/sse.js"></script>
  <style>
    body { font-family: system-ui, sans-serif; max-width: 40rem; margin: 2rem auto; padding: 0 1rem; }
    form { display: flex; gap: 0.5rem; margin: 0.5rem 0 1rem; }
    input { flex: 1; padding: 0.5rem; }
    .response { background: #f1f5f9; padding: 1rem; border-radius: 0.5rem; min-height: 4rem; white-space: pre-wrap; }
    .hint { color: #64748b; font-size: 0.875rem; }
    .prompt { color: #475569; margin-bottom: 0.5rem; }
  </style>
</head>
<body>
<main>
  <h1>{{ title }}</h1>
  <p class="hint">Simulated tokens — no API keys required.</p>

  <h2>TemplateStream</h2>
  <p class="hint">Plain form POST → full-page chunked HTML.</p>
  <form action="/ask" method="post" hx-target="body" hx-select="unset">
    {{ csrf_field() }}
    <input name="prompt" aria-label="Prompt" placeholder="Hello" autocomplete="off">
    <button type="submit">Stream</button>
  </form>

  <h2>EventStream</h2>
  <p class="hint">htmx POST → Fragment panel → parametric SSE.</p>
  <form hx-post="/stream/start"
        hx-target="#sse-section"
        hx-swap="innerHTML"
        hx-on::after-request="if(event.detail.successful) this.reset()"
        method="post">
    {{ csrf_field() }}
    <input name="prompt" aria-label="Prompt" placeholder="Hello" autocomplete="off">
    <button type="submit">Stream SSE</button>
  </form>
  <div id="sse-section"><p class="hint">Submit to stream here.</p></div>
</main>
</body>
</html>
"""

STREAM_RESPONSE_HTML = """\
<!DOCTYPE html>
<html lang="en">
<head><meta charset="utf-8"><title>Response</title></head>
<body>
<main>
  <p class="prompt">Prompt: {{ prompt }}</p>
  <div class="response">{% async for chunk in stream %}{{ chunk }}{% end %}</div>
  <p><a href="/">← Back</a></p>
  {% block token %}<span>{{ text_chunk }}</span>{% endblock %}
</main>
</body>
</html>
"""

STREAM_SSE_PANEL_HTML = """\
{% block sse_panel %}
<div hx-ext="sse" sse-connect="{{ stream_url }}" sse-close="close" hx-disinherit="hx-target hx-swap" style="display: contents">
  <p class="prompt">Prompt: {{ prompt }}</p>
  <div class="response" sse-swap="message" hx-target="this" hx-swap="beforeend"></div>
</div>
{% endblock %}
"""

STREAM_CONFTEST_PY = """\
import os

os.environ.setdefault("STREAM_DELAY", "0")
"""

STREAM_TEST_APP_PY = """\
\"\"\"Smoke tests for {name}.\"\"\"

import importlib.util
import re
from pathlib import Path

import pytest

from chirp.testing import TestClient


@pytest.fixture
def app_module():
    root = Path(__file__).resolve().parent.parent
    spec = importlib.util.spec_from_file_location("stream_app", root / "app.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestStreamScaffold:
    async def test_index(self, app_module) -> None:
        async with TestClient(app_module.app) as client:
            response = await client.get("/")
            assert response.status == 200

    async def test_template_stream_renders_generated_chunks(self, app_module) -> None:
        async with TestClient(app_module.app) as client:
            page = await client.get("/")
            csrf = re.search(r'name="_csrf_token" value="([^" ]+)"', page.text).group(1)
            cookie = next(value.split(";")[0] for name, value in page.headers if name == "set-cookie")
            response = await client.post(
                "/ask",
                data={{"prompt": "Hello", "_csrf_token": csrf}},
                headers={{"Content-Type": "application/x-www-form-urlencoded", "Cookie": cookie}},
            )
            assert response.status == 200
            assert "You asked: Hello" in response.text
            assert "Tokens stream to the browser" in response.text

    async def test_sse_start_uses_htmx(self, app_module) -> None:
        async with TestClient(app_module.app) as client:
            page = await client.get("/")
            csrf = re.search(r'name="_csrf_token" value="([^" ]+)"', page.text).group(1)
            cookie = next(value.split(";")[0] for name, value in page.headers if name == "set-cookie")
            response = await client.post(
                "/stream/start",
                data={{"prompt": "Hello", "_csrf_token": csrf}},
                headers={{
                    "Content-Type": "application/x-www-form-urlencoded",
                    "HX-Request": "true",
                    "Cookie": cookie,
                }},
            )
            assert response.status == 200
            assert 'hx-swap="beforeend"' in response.text
"""
