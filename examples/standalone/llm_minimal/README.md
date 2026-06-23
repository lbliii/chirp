# LLM Minimal — streaming tokens, no Ollama required

The smallest streaming-LLM example in Chirp. Tokens type out in the browser —
still just Python, no frontend build. It uses a **simulated** token stream by
default, so it runs (and tests) with no Ollama and no API keys.

This fills the gap between two existing examples:

- `chirpui/llm_playground` — ChirpUI-only, more to read before the AI part.
- `standalone/ollama` — a real local LLM, but heavier (tools, agent loop, httpx).

Start here if you are AI-curious and want the 5-minute path.

## Run

```bash
# From the chirp repo root
PYTHONPATH=src python examples/standalone/llm_minimal/app.py
```

Open [http://localhost:8000](http://localhost:8000).

- **TemplateStream** — submit the first form; the browser navigates to a full
  page that streams the answer in one chunked HTML response.
- **EventStream** — submit the second form; htmx swaps in an SSE panel that
  streams one Fragment per token.

## Transport × client shape

Pick the transport first, then wire the client to match:

| | **Full-page client** | **htmx swap client** |
|---|---|---|
| **Chunked HTTP (`TemplateStream`)** | plain `<form method="post">` | not supported — use `EventStream` or `Fragment` |
| **SSE (`EventStream`)** | rare | `Fragment` scaffold + parametric `sse-connect` |

This example shows both safe pairings side by side. Chirp's
`template_stream_client_shape` contract warns if you htmx-swap a
`TemplateStream` response into a div.

## TemplateStream vs EventStream — the choice this example makes

The same simulated stream is rendered two ways so you can compare:

| | `TemplateStream` (`/ask`) | `EventStream` (`/stream`) |
|---|---|---|
| **Template** | `{% async for token in stream %}` | a `{% block token %}` re-rendered per token |
| **Transport** | one chunked HTML response body | Server-Sent Events |
| **Work** | O(n) — one template render | O(n) — one small Fragment per token |
| **Client** | plain form POST → full page | htmx POST → `Fragment` panel → SSE |
| **Reach for it when** | a single request streams one growing answer | you fan out to multiple targets, reconnect, or push tool/status events too |

**This example recommends `TemplateStream` as the default for a single chat
answer**: it is the least machinery for "stream one response into one place."
Reach for `EventStream` when you need SSE semantics — multiple swap targets,
reconnection, or interleaving status/tool events with tokens (see the
`standalone/ollama` example for the richer version).

Both routes call the same `get_stream(prompt)` async iterator, which is the
only seam you replace to go from simulated to real tokens.

## What it shows

- **Simulated stream** — no Ollama, no keys; the default path.
- **`TemplateStream` + `{% async for %}`** — chunked HTML, O(n) render.
- **`EventStream` + `Fragment`-per-token** — the SSE alternative, side by side.
- **One swap seam** — `get_stream()` is the only thing a real LLM changes.

## Optional: stream from a real local LLM (Ollama)

The example degrades gracefully — if Ollama is not reachable it falls back to
the simulated stream — so this step is entirely optional.

```bash
# 1. Install the optional AI extra (adds httpx for chirp.ai.LLM)
pip install chirp[ai]

# 2. Install Ollama (https://ollama.com/download) and pull a small model
ollama pull llama3.2

# 3. Start Ollama, then run the app with USE_OLLAMA=1
ollama serve                      # one terminal
USE_OLLAMA=1 PYTHONPATH=src python examples/standalone/llm_minimal/app.py
```

`get_stream()` then streams from `chirp.ai.LLM("ollama:llama3.2").stream(prompt)`
instead of the canned text — every other line of the example stays the same.

## Testing

Tests use the simulated stream, so no server, model, or API key is required:

```bash
pytest examples/standalone/llm_minimal/ -q
```

Good-first issue acceptance (`@pytest.mark.issue(454)`) covers both streaming
paths without Ollama.
