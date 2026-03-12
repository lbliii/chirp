"""SSE project scaffolding templates (--sse)."""

SSE_APP_PY = """\
from chirp import App, Request
from chirp.streaming import EventStream, Fragment
from chirp.templating import Template

app = App()


@app.route("/")
async def index(request: Request) -> Template:
    return Template("index.html", greeting="Hello, world!")


@app.route("/stream", referenced=True)
async def stream(request: Request) -> EventStream:
    async def events():
        yield Fragment("index.html", "stream_block", text="Hello from SSE!")

    return EventStream(events())
"""

SSE_INDEX_HTML = """\
{% extends "chirp/layouts/boost.html" %}
{% block title %}{{ greeting }}{% end %}
{% block content %}
<h1>{{ greeting }}</h1>
<div hx-ext="sse" sse-connect="/stream" hx-disinherit="hx-target hx-swap">
  <div sse-swap="stream_block" hx-target="this">
    <span>Waiting for stream...</span>
  </div>
</div>
{% end %}

{% block stream_block %}
<p>{{ text }}</p>
{% end %}
"""
