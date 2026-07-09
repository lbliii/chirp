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

<!-- example-inventory:standalone:start -->
- [`accessibility`](accessibility/) — supporting, tier 2
- [`api`](api/) — supporting, tier 1
- [`auth`](auth/) — canonical, tier 2
- [`chat`](chat/) — supporting, tier 2
- [`contacts`](contacts/) — canonical, tier 1
- [`custom_middleware`](custom_middleware/) — supporting, tier 2
- [`dashboard`](dashboard/) — supporting, tier 2
- [`dashboard_live`](dashboard_live/) — supporting, tier 3
- [`devtools_htmx4`](devtools_htmx4/) — supporting, tier 2
- [`docs_site`](docs_site/) — canonical, tier 2
- [`form_get`](form_get/) — supporting, tier 1
- [`freeze_site`](freeze_site/) — canonical, tier 2
- [`hackernews`](hackernews/) — supporting, tier 3
- [`hello`](hello/) — canonical, tier 1
- [`htmx_managed`](htmx_managed/) — experimental, tier 2
- [`islands`](islands/) — supporting, tier 2
- [`islands_swap`](islands_swap/) — experimental, tier 2
- [`kanban`](kanban/) — canonical, tier 3
- [`llm_minimal`](llm_minimal/) — canonical, tier 1
- [`llm_streaming_kida`](llm_streaming_kida/) — supporting, tier 2
- [`mutation_result`](mutation_result/) — supporting, tier 2
- [`nojs_floor`](nojs_floor/) — canonical, tier 2
- [`ollama`](ollama/) — canonical, tier 3
- [`oob_layout_chain`](oob_layout_chain/) — experimental, tier 3
- [`optimistic_apply`](optimistic_apply/) — experimental, tier 3
- [`passkeys_minimal`](passkeys_minimal/) — supporting, tier 3
- [`pokedex`](pokedex/) — supporting, tier 2
- [`production`](production/) — canonical, tier 3
- [`query_search`](query_search/) — canonical, tier 3
- [`reactive_tasks`](reactive_tasks/) — canonical, tier 3
- [`returns_gallery`](returns_gallery/) — canonical, tier 2
- [`search`](search/) — supporting, tier 1
- [`shapes_workspaces`](shapes_workspaces/) — experimental, tier 3
- [`signup`](signup/) — supporting, tier 2
- [`sse`](sse/) — canonical, tier 2
- [`sse_reconnect`](sse_reconnect/) — supporting, tier 3
- [`static_site`](static_site/) — supporting, tier 2
- [`streaming`](streaming/) — canonical, tier 2
- [`survey`](survey/) — supporting, tier 2
- [`suspense_dashboard`](suspense_dashboard/) — supporting, tier 2
- [`theming`](theming/) — supporting, tier 1
- [`todo`](todo/) — canonical, tier 2
- [`tools`](tools/) — supporting, tier 2
- [`tools_hitl`](tools_hitl/) — experimental, tier 3
- [`upload`](upload/) — supporting, tier 2
- [`webmcp_form`](webmcp_form/) — experimental, tier 2
- [`wizard`](wizard/) — supporting, tier 2
<!-- example-inventory:standalone:end -->

## Validation Expectation

If a standalone example requires a ChirpUI shell or `delegation=True`, treat that as a bug in the standalone support lane.

Keep standalone and ChirpUI examples separate on purpose: standalone examples
make the raw return-type and htmx contracts easy to reason about, while ChirpUI
examples prove the same contracts inside app-shell and component composition.
