# RFC: RAG integration strategy — optional plugin, not in-core vector store

**Status**: Accepted design gate for Phase 3 epic #423 / issue #439. Implementation tracked in #440.
**Date**: 2026-06-22
**Scope**: `chirp.ai.streaming`, optional `chirp-rag` / LlamaIndex bridge, examples, contract checks (if any)
**Related**: #420 (AI saga), #423 (Phase 3), #440 (vector plugin), `plan/drafted/rfc-ai-friendly-chirp.md`

> **North star:** Chirp streams retrieved context into HTML — it does not own embeddings research infrastructure.

---

## 1. Problem

Apps want semantic retrieval (vector search, reranking, chunking) alongside Chirp's existing **LLM → SSE → Fragment** transport. Building an in-core vector store would duplicate LlamaIndex, pgvector adapters, and embedding pipelines that mature libraries already solve.

Chirp already ships a RAG-shaped UI helper:

```python
EventStream(stream_with_sources(
    llm.stream(prompt_with_context),
    "ask.html",
    sources_block="sources",
    sources=docs,
    response_block="answer",
))
```

The gap is not transport — it is **retrieval strategy, packaging, and optional bridge APIs** so apps do not fork `stream_with_sources` per vendor.

---

## 2. Decision summary

| Layer | Owner | Notes |
|-------|-------|-------|
| Retrieval (embed, index, query) | **Optional plugin** or app code | Never in `src/chirp/core` |
| Prompt assembly | App or thin helper | App controls context window / citations |
| LLM call | `chirp.ai.LLM` | Stable; provider adapters in core |
| UI transport | `stream_with_sources` + templates | Core moat; sources block first, answer streams |

**Bright line:** No embedding pipeline, vector DB driver, or chunk store in core. Optional extra: `pip install chirp[rag]` or separate `chirp-rag` package.

---

## 3. Target patterns

### 3.1 App-authored retrieval (v0 — always valid)

```python
@app.route("/ask", methods=["POST"])
async def ask(request: Request):
    question = (await request.form())["question"]
    docs = await keyword_search(question)  # app-owned
    prompt = f"Context:\n{format_docs(docs)}\n\nQ: {question}"
    return EventStream(stream_with_sources(
        llm.stream(prompt),
        "ask.html",
        sources=docs,
        sources_block="sources",
        response_block="answer",
    ))
```

No framework hook required. Contract checks apply only if the app registers RAG templates with `sse-swap` / `signal()` bindings (existing hypermedia rules).

### 3.2 Optional retrieval bridge (#440)

```python
from chirp_rag import RetrievalBridge  # or chirp.ext.rag when packaged

bridge = RetrievalBridge.from_env()  # LlamaIndex, minimal embeddings, or pgvector

@app.route("/ask", methods=["POST"])
async def ask(request: Request):
    question = (await request.form())["question"]
    hits = await bridge.retrieve(question, top_k=5)
    return EventStream(stream_with_sources(
        llm.stream(bridge.format_prompt(question, hits)),
        "ask.html",
        sources=hits,
        sources_block="sources",
        response_block="answer",
    ))
```

Bridge responsibilities:

- Embed + query (delegates to LlamaIndex or minimal local stack)
- Return **plain records** (`title`, `snippet`, `url`, `score`) — not Chirp types
- Optional `format_prompt(question, hits) -> str` helper

Bridge non-responsibilities:

- SSE wiring (app uses `stream_with_sources`)
- Session / tenant scoping (app passes filters)
- Tool registration (retrieval is not an MCP tool unless the app chooses)

### 3.3 Agent + retrieval tool (optional composition)

Retrieval may also be exposed as `@app.tool("search_docs")` for agent loops. That path uses existing `ToolRegistry` + `AgentRun` — no special RAG runtime in core. The tool handler calls the bridge; the agent streams citations through normal tool-result → assistant message flow.

---

## 4. Packaging

| Install | Contents |
|---------|----------|
| `pip install chirp[ai]` | LLM + streaming helpers only (today) |
| `pip install chirp[rag]` | Pulls bridge deps (LlamaIndex *or* minimal: `numpy` + optional `sentence-transformers`) |
| Separate PyPI `chirp-rag` | Preferred if deps are heavy; core stays lean |

Core MUST NOT import bridge modules at startup. Bridge loads only when app imports it.

---

## 5. Contract checks (optional, Phase 3+)

If RAG templates become common in scaffolds, add **opt-in** categories (provisional):

| Category | Severity | When |
|----------|----------|------|
| `rag_sources_block` | WARNING | `sources_block` named in route but template block missing |
| `rag_empty_sources` | INFO | Route references retrieval but no `sources=` in handler metadata (static analysis limited) |

No vector-index health checks in core — ops concern of the bridge.

---

## 6. Non-goals

- In-core vector store (Chroma, pgvector driver, etc.)
- Automatic citation extraction from model output
- Hybrid search implementation
- Document ingestion UI
- LangSmith / eval dataset storage

---

## 7. Success criteria (#439)

- [x] RFC lands with packaging boundary and `stream_with_sources` as canonical UI path
- [ ] #440 implements minimal bridge OR documents LlamaIndex adapter with example
- [ ] Example README shows retrieval → sources block → streamed answer (no core vector code)

---

## 8. References

- `src/chirp/ai/streaming.py` — `stream_with_sources`
- `plan/drafted/rfc-ai-friendly-chirp.md` §4.4, §8
- Issue #440 — plugin implementation
