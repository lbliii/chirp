# AI Integration Steward

This domain represents the optional AI/LLM extra: provider abstractions, structured outputs, streaming helpers, and related errors.

Related docs:
- root `AGENTS.md`
- `pyproject.toml`
- `examples/chirpui/llm_playground/README.md`
- `examples/standalone/ollama/README.md`

## Point Of View

The app author opting into LLM streaming while still using Chirp's HTML/streaming contracts instead of a separate API layer.

## Protect

- AI remains an optional extra with clear missing-dependency guidance.
- Token/LLM streaming integrates with Chirp streaming types without blurring `Stream`, `Suspense`, and `EventStream`.
- Provider errors are actionable and do not leak secrets.
- Structured output behavior is deterministic enough to test.
- Network/provider assumptions stay out of core runtime dependencies.

## Contract Checklist

- Inspect providers, streaming helpers, structured outputs, errors, examples, optional deps, docs, and tests together.
- Update README optional extras, AI examples, public API docs, and changelog when behavior changes.
- Run relevant AI/example tests such as `uv run pytest examples/chirpui/llm_playground examples/standalone/ollama -q` when changing this surface.
- Run `uv run ruff check src/chirp/ai`.

## Advocate

- Provider-neutral examples that stream HTML safely.
- Redaction tests for provider errors and logs.
- Clear docs for when to use SSE versus streaming HTML for AI output.

## Serve Peers

- Give `templating` and `realtime` realistic streaming use cases.
- Give `examples` useful LLM demos without unstable public promises.
- Tell `security` when secrets or provider errors need redaction.

## Do Not

- Make AI dependencies mandatory.
- Add hidden network calls to import/setup paths.
- Build a JSON API side channel for LLM output.

## Own

- `src/chirp/ai/`.
- LLM/AI examples and any tests that cover provider, structured, and streaming helpers.
- Optional-extra docs for AI features.
