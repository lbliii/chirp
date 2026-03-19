# Standalone Chirp Examples

These examples are the baseline Chirp lane: no `chirp_ui`, no app shell, and no dependency on `delegation=True` for correctness.

They are the reference point for:

- raw HTMX fragments and forms
- SSE and streaming
- middleware, auth, and data integration
- API-only and HTML-first examples

## Run From Repo Root

```bash
cd /Users/llane/Documents/github/python/b-stack/chirp
source .venv/bin/activate
PYTHONPATH=src python examples/standalone/hello/app.py
```

## Representative Examples

- `hello`: minimal routing and return-value negotiation
- `contacts`: canonical HTMX CRUD
- `sse`: fragment-driven server-sent events
- `streaming`: `Stream()` with concurrent context loading
- `ollama`: local LLM chat without ChirpUI
- `kanban`: auth, CSRF, OOB, and live updates without app shell
- `production`: security stack

## Inventory

- `accessibility`
- `api`
- `auth`
- `chat`
- `contacts`
- `custom_middleware`
- `dashboard`
- `dashboard_live`
- `form_get`
- `hackernews`
- `hello`
- `islands`
- `islands_swap`
- `kanban`
- `llm_streaming_kida`
- `ollama`
- `oob_layout_chain`
- `pokedex`
- `production`
- `search`
- `signup`
- `sse`
- `static_site`
- `streaming`
- `survey`
- `theming`
- `todo`
- `tools`
- `upload`
- `wizard`

## Validation Expectation

If a standalone example requires a ChirpUI shell or `delegation=True`, treat that as a bug in the standalone support lane.
