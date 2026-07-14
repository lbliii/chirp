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

from chirp import App
from chirp.testing import TestClient


app = App()


@app.route("/")
async def index():
    return "Hello, world!"


class TestSmoke:
    def test_index(self) -> None:
        client = TestClient(app)
        response = client.get("/")
        assert response.status == 200
"""

SSE_APP_PY = """\
from chirp import App, AppConfig, EventStream, Fragment, Request, Template

app = App(AppConfig.from_env(worker_mode="async"))


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
