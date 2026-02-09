# Ollama Chat

Talk to a local LLM that can call tools — with a live activity dashboard.

This example connects [Chirp](https://github.com/llane/chirp) to
[Ollama](https://ollama.com), giving you a chat interface where the model
can manage notes, tell the time, and do math. Tool calls flow through
Chirp's `ToolRegistry` and light up the activity panel in real-time via
Server-Sent Events.

## What it demonstrates

- **Token-by-token streaming** — assistant response streams via SSE with a blinking cursor
- **`@app.tool()`** — register Python functions as callable tools
- **Agent loop** — multi-turn tool calling (Ollama calls tools, gets results, responds)
- **`ToolEventBus` + SSE** — tool calls stream live to the activity panel
- **Stream toggle** — switch between streaming and instant mode in the UI
- **htmx** — no JavaScript needed for the chat UI
- **Per-worker httpx client** — free-threading safe HTTP via `ContextVar`

## Setup

### 1. Install Ollama

```bash
# macOS
brew install ollama

# Linux / other
# See https://ollama.com/download
```

### 2. Pull the model

```bash
ollama pull llama3.2
```

### 3. Start Ollama

```bash
ollama serve
```

### 4. Run the app

```bash
# From the chirp repo root
python examples/ollama/app.py
```

Open [http://localhost:8000](http://localhost:8000) and start chatting.

## Tools available to the model

| Tool | What it does |
|------|-------------|
| `add_note(text, tag)` | Save a note with an optional tag |
| `list_notes()` | List all saved notes |
| `search_notes(query)` | Search notes by substring |
| `get_current_time()` | Current date and time (UTC) |
| `calculate(expression)` | Evaluate a math expression |

Try asking things like:

- "What time is it?"
- "Remember to buy groceries"
- "What's 42 * 17 + 3?"
- "What notes do I have?"

## Architecture

```
Browser ──POST /chat──▶ Chirp (saves message, returns scaffolding)
   │                      │
   │◀─ user bubble + ─────┘  (htmx swaps HTML)
   │   SSE-connected div
   │
   ├──GET /chat/stream──▶ Chirp ──POST /api/chat──▶ Ollama
   │                      │                          │
   │                      │◀── tool_calls ───────────┘
   │                      │
   │                      ├──▶ ToolRegistry.call_tool()
   │                      │       └──▶ ToolEventBus.emit()
   │                      │
   │◀─ SSE /feed ─────────┤  (activity panel lights up)
   │                      │
   │                      ├──▶ Ollama (streaming, with tool results)
   │                      │◀── tokens ──────────────┘
   │                      │
   │◀─ SSE tokens ────────┘  (assistant bubble grows word-by-word)
```

The key insight: `ToolRegistry.call_tool()` is the bridge. It dispatches
the tool, fires the event bus (activity panel lights up), and returns the
result to the agent loop. Zero glue code.

When streaming is enabled (default), the POST returns scaffolding HTML
with an `sse-connect` attribute. htmx opens a second SSE connection to
`/chat/stream`, which runs the agent loop and yields tokens as they
arrive. A `done` SSE event closes the connection via `sse-close`.

## Testing

Tests mock Ollama at the module level — no running server needed:

```bash
python -m pytest examples/ollama/test_app.py -v
```
