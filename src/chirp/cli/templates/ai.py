"""AI scaffold templates (--ai)."""

AI_APP_PY = """\
\"\"\"AI chat scaffold — tools, SSE activity feed, secure stack.\"\"\"

import os
from pathlib import Path

from chirp import App, AppConfig, EventStream, Fragment, Request, Template, secure_stack
from chirp.ai import AgentRun, InMemoryConversationStore, LLM

TEMPLATES_DIR = Path(__file__).parent / \"templates\"

app = App(AppConfig(template_dir=TEMPLATES_DIR, worker_mode=\"async\"))
secure_stack(app)

_store = InMemoryConversationStore()
_llm = LLM(os.environ.get(\"CHIRP_LLM\", \"openai:gpt-4o-mini\"))
_pending_user: str | None = None


@app.tool(\"get_time\", description=\"Return the current UTC time\")
def get_time() -> str:
    from datetime import UTC, datetime

    return datetime.now(UTC).isoformat()


@app.tool(\"echo\", description=\"Echo a message back\")
def echo(message: str) -> str:
    return message


def _agent() -> AgentRun:
    app._ensure_frozen()
    registry = app._tool_registry
    assert registry is not None
    return AgentRun(_llm, registry, store=_store, system=\"You are a helpful assistant.\")


@app.route(\"/\")
async def index():
    messages = await _store.load(\"default\")
    return Template(\"chat.html\", messages=messages)


@app.route(\"/chat\", methods=[\"POST\"], name=\"chat.post\")
async def post_chat(request: Request):
    global _pending_user
    form = await request.form()
    user_message = (form.get(\"message\") or \"\").strip()
    if not user_message:
        return Fragment(\"chat.html\", \"empty_response\")
    _pending_user = user_message
    return Fragment(\"chat.html\", \"stream_start\", user_content=user_message)


@app.route(\"/chat/stream\", referenced=True)
def chat_stream():
    async def generate():
        global _pending_user
        user_message = _pending_user or \"\"
        _pending_user = None
        if not user_message:
            return
        agent = _agent()
        from chirp.ai.events import TokenEvent

        async for event in agent.stream(user_message):
            if isinstance(event, TokenEvent):
                yield Fragment(\"chat.html\", \"stream_token\", token=event.text)

    return EventStream(generate())


@app.route(\"/feed\", referenced=True)
def feed():
    async def generate():
        async for event in app.tool_events.subscribe():
            yield Fragment(\"chat.html\", \"activity_row\", event=event)

    return EventStream(generate())


if __name__ == \"__main__\":
    app.run()
"""

AI_CHAT_HTML = """\
{% extends \"chirp/layouts/boost.html\" %}
{% block title %}AI Chat{% end %}
{% block content %}
<h1>AI Chat</h1>
<div id=\"messages\">
{% for msg in messages %}
<p><strong>{{ msg.role }}:</strong> {{ msg.content }}</p>
{% end %}
</div>
<form hx-post=\"/chat\" hx-target=\"#chat-input\" hx-swap=\"outerHTML\">
  <div id=\"chat-input\">
    <input name=\"message\" placeholder=\"Ask anything...\" autocomplete=\"off\" />
    <button type=\"submit\">Send</button>
  </div>
</form>
<div id=\"stream-region\"></div>
{% end %}

{% block stream_start %}
<div id=\"stream-region\" hx-ext=\"sse\" sse-connect=\"/chat/stream\" sse-swap=\"stream_token\">
  <p><strong>user:</strong> {{ user_content }}</p>
  <p id=\"assistant-stream\"></p>
</div>
{% end %}

{% block stream_token %}
<p id=\"assistant-stream\">{{ token }}</p>
{% end %}

{% block activity_row %}
<div class=\"activity\">{{ event.tool_name }}({{ event.arguments | format_json }})</div>
{% end %}

{% block empty_response %}
<p class=\"error\">Enter a message.</p>
{% end %}
"""

AI_TEST_APP_PY = """\
\"\"\"Smoke tests for {name}.\"\"\"

from pathlib import Path

import pytest

from app import app
from chirp.testing import TestClient


@pytest.fixture
def example_app():
    return app


class TestSmoke:
    @pytest.mark.asyncio
    async def test_index(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get(\"/\")
            assert response.status == 200
            assert \"AI Chat\" in response.text
"""

AI_ENV_EXAMPLE = """\
# LLM provider string (provider:model)
CHIRP_LLM=openai:gpt-4o-mini
OPENAI_API_KEY=sk-...
CHIRP_SECRET_KEY=change-me-in-production
"""
