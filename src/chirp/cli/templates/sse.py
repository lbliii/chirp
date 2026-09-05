"""SSE project scaffolding templates (--sse)."""

STYLE_CSS = """\
*,
*::before,
*::after {{
    box-sizing: border-box;
}}

body {{
    font-family: system-ui, -apple-system, sans-serif;
    line-height: 1.6;
    max-width: 40rem;
    margin: 2rem auto;
    padding: 0 1rem;
    color: #1a1a1a;
}}

h1 {{
    font-weight: 600;
}}
"""

TEST_APP_PY = """\
\"\"\"Basic smoke tests for {name}.\"\"\"

from app import app
from chirp.testing import TestClient


class TestSmoke:
    async def test_index(self) -> None:
        async with TestClient(app) as client:
            response = await client.get("/")
            assert response.status == 200

"""

SSE_APP_PY = """\
from project_paths import ROOT

from chirp import App, AppConfig, EventStream, Fragment, Request, Template, secure_stack

app = App(AppConfig.from_env(template_dir=ROOT / "templates", csp_nonce_enabled=True, worker_mode="async"))
for middleware in secure_stack(app.config):
    app.add_middleware(middleware)


@app.route("/")
async def index(request: Request) -> Template:
    return Template("index.html", greeting="Hello, world!")


@app.route("/stream", referenced=True)
async def stream(request: Request) -> EventStream:
    async def events():
        yield Fragment("index.html", "stream_block", text="Hello from SSE!")

    return EventStream(events())


if __name__ == "__main__":
    app.run()
"""

SSE_INDEX_HTML = """\
{% extends "chirp/layouts/boost.html" %}
{% block title %}{{ greeting }}{% end %}
{% block content %}
<h1>{{ greeting }}</h1>
<p>Waiting for stream...</p>
{% end %}

{% block sse_scope %}
{% from "chirp/sse.html" import sse_scope %}
{{ sse_scope("/stream", swap="stream_block") }}
{% end %}

{% block stream_block %}
<p>{{ text }}</p>
{% end %}
"""
