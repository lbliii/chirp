<!-- generated from .stewards/manifest.toml — edit the manifest, not this file -->

# Steward: ai

Keep LLM providers, structured output, and token streaming optional, offline-testable, and hypermedia-native.

Ordinary work: use this map directly with the root map and run only affected checks.
Do not open `.stewards/PROTOCOL.md` or `.stewards/manifest.toml` unless the task is an explicit review/audit or steward-network maintenance.

## Protects

| Invariant | Sev | Backing | Proof / anchor |
| --- | --- | --- | --- |
| AI providers, structured output, approvals, and streaming remain offline-testable optional behavior. | P1 | machine-backed | `uv run pytest tests/test_ai -q` (`ai-suite`) |

## Guardrails

- AI dependencies remain optional and provider absence names the required install or configuration.
- Committed examples contain no keys, private prompts, or internal endpoints.

## Edges

- streams-through → **realtime** (SSE when selected)
- optionally-renders → **markdown** (model output)

## Owns

- **code:** `src/chirp/ai/`
- **tests:** `tests/test_ai/`
- **docs:** `examples/standalone/llm_minimal/`
