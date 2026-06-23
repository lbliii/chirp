---
title: Testing AI routes
description: Mock LLM providers and assert on agent tool loops with TestClient
draft: false
weight: 35
lang: en
type: doc
tags: [testing, ai, llm, agents]
keywords: [testing, ai, llm, mock, eval, agent, sse]
category: guide
---

## What it is

Chirp AI routes and :class:`~chirp.ai.agent.AgentRun` loops call remote LLM
providers over HTTP. For CI you mock that HTTP at the **httpx transport
layer** — the same pattern used in ``examples/standalone/ollama/test_app.py``,
now packaged as ``chirp.testing.eval`` helpers.

No live API keys. No provider SDKs in tests.

## Quick start

```python
import pytest
from chirp.testing import TestClient, LLMScript, install_llm_script, openai_completion, openai_tool_call

@pytest.mark.asyncio
async def test_chat_complete(example_app, example_module, monkeypatch):
    tracker = install_llm_script(
        monkeypatch,
        LLMScript(
            completes=[
                openai_completion(tool_calls=[openai_tool_call("get_time")]),
                openai_completion(""),
            ],
            stream_tokens=["It is noon UTC."],
        ),
    )
    await example_module._store.append("default", {"role": "user", "content": "What time?"})

    async with TestClient(example_app) as client:
        response = await client.fragment("/chat/complete")
        assert "noon" in response.text

    assert tracker.complete_calls == 2
```

## Helpers

| Helper | Purpose |
|--------|---------|
| ``LLMScript`` | Scripted complete + stream responses |
| ``install_llm_script()`` | Patch httpx for AgentRun / LLM calls |
| ``openai_completion()`` | Build OpenAI-compatible completion JSON |
| ``openai_tool_call()`` | Build a single tool-call entry |
| ``collect_sse_message_text()`` | Join SSE ``message`` event payloads |
| ``assert_tool_messages_contain()`` | Assert tool results in a message list |

## Structured output tests

For unit tests against :class:`~chirp.LLM` directly, patch the transport and
exercise ``generate(MyModel, prompt=...)``. Structured mode retries on
``StructuredOutputError`` (default 2 retries) and accepts frozen dataclasses or
optional Pydantic ``BaseModel`` subclasses.

```python
from chirp.testing.eval import install_mock_transport

# See tests/test_ai/test_phase3.py for retry + native json_schema examples.
```

## When to use eval helpers vs contract checks

- **Eval helpers** — regression-test LLM routes, tool rounds, and SSE chat
  output per request.
- **``app.check()``** — startup hypermedia contract checks (routes, fragments,
  SSE wiring). Complementary, not a substitute.

See also: [[docs/quality/testing/test-client|TestClient]], [[docs/quality/testing/assertions|Assertions]].
