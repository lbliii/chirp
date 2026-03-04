# LLM Streaming with Kida — TemplateStream

`return TemplateStream("response.html", stream=..., prompt=...)` where the
template contains `{% async for token in stream %}`. Kida's `render_stream_async`
yields chunks as the template iterates — O(n) work, not Fragment-per-token.

## Run

```bash
cd examples/llm_streaming_kida && python app.py
```

Submit a prompt. The response streams token-by-token as the template iterates.

## What It Shows

- **TemplateStream return type** — For templates with `{% async for %}` or `{{ await }}`
- **O(n) rendering** — One template render, chunks as it iterates (vs Fragment-per-token)
- **Simulated stream** — No Ollama required; set `USE_OLLAMA=1` for real LLM

## TemplateStream vs Fragment-per-token

| | TemplateStream | Fragment-per-token (SSE) |
|---|----------------|---------------------------|
| **Template** | `{% async for token in stream %}` | Block re-rendered per token |
| **Work** | O(n) | O(n²) |
| **Response** | Chunked HTML | SSE events |
| **Use case** | Single request, chunked body | htmx SSE, multi-target swaps |
