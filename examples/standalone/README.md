# Standalone Chirp Examples

These examples are the baseline Chirp lane: no `chirp_ui`, no app shell, and no dependency on `delegation=True` for correctness.

They are the reference point for:

- raw HTMX fragments and forms
- SSE and streaming
- middleware, auth, and data integration
- API-only and HTML-first examples

## Run From Repo Root

```bash
# From the repo root:
source .venv/bin/activate
PYTHONPATH=src python examples/standalone/hello/app.py
```

## Representative Examples

- `returns_gallery`: **start here** — every Chirp return type on one page
- `hello`: minimal routing and return-value negotiation
- `contacts`: canonical HTMX CRUD
- `sse`: fragment-driven server-sent events
- `streaming`: `Stream()` with concurrent context loading
- `llm_minimal`: smallest streaming-LLM example — simulated tokens, no Ollama
- `ollama`: local LLM chat without ChirpUI
- `kanban`: auth, CSRF, OOB, and live updates without app shell
- `docs_site`: DocsPlugin, autodoc, search, and tool docs without ChirpUI
- `freeze_site`: markdown content and static output with layout composition
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
- `docs_site`
- `form_get`
- `freeze_site`
- `hackernews`
- `hello`
- `htmx_managed`
- `islands`
- `islands_swap`
- `kanban`
- `llm_minimal`
- `llm_streaming_kida`
- `nojs_floor`
- `ollama`
- `oob_layout_chain`
- `pokedex`
- `production`
- `returns_gallery`
- `search`
- `signup`
- `sse`
- `sse_reconnect`
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

Keep standalone and ChirpUI examples separate on purpose: standalone examples
make the raw return-type and htmx contracts easy to reason about, while ChirpUI
examples prove the same contracts inside app-shell and component composition.
