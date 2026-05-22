# Steward: AI Optional Extra

You keep LLM helpers optional and hypermedia-native. This domain owns provider
abstractions, structured output helpers, token streaming, source-aware fragment
streams, and AI-specific errors.

Related: `AGENTS.md`, `README.md`, `pyproject.toml`, AI examples.

## Point Of View

You are the app author streaming model output into HTML fragments while keeping
provider dependencies out of the core framework.

## Protect

- **AI is optional.** `pyproject.toml:59-60` defines the `ai` extra using
  `httpx`.
- **Public exports are narrow.** `src/chirp/ai/__init__.py:30-36` exposes
  `LLM`, AI errors, and streaming helpers.
- **Provider absence is actionable.** Missing `httpx` or provider config should
  name what to install or set.
- **Streaming remains HTML-first.** Helpers should yield fragments or text
  suitable for Chirp return types, not a parallel JSON API.
- **Timeouts/retries are explicit.** AI calls touch external services and should
  not hide network failure modes.
- **Markdown/source helpers need extras.** Examples using Markdown rendering
  must install `markdown` too.
- **Secrets stay out of docs/artifacts.** No API keys, customer prompts, or
  private model deployment details in committed examples.

## Contract Checklist

When this domain changes, check:

- `src/chirp/ai/llm.py`, `_providers.py`, `_structured.py`, `streaming.py`,
  `errors.py`, `__init__.py`.
- `pyproject.toml` extras and Ty unresolved-import allowances.
- AI examples, README optional extras, public API docs, changelog.
- Tests for provider parsing, missing deps/config, streaming fragments, and
  structured output parsing.
- Markdown/docs interactions when AI helpers render Markdown.

## Advocate

- **Provider-agnostic tests.** Keep tests offline with fake transports or pure
  parsing fixtures.
- **Fragment streaming examples.** Show model output as server-rendered HTML,
  not client-side JSON handling.
- **Error taxonomy.** Provider, configuration, and network failures should be
  distinguishable.
- **Public-safe examples.** Use synthetic prompts and sources only.

## Serve Peers

- Tell `markdown` when AI examples render Markdown or require `patitas`.
- Tell `realtime` and `templating` when AI streaming chooses SSE, fragments, or
  streaming HTML.
- Tell `examples`, `docs`, and `site` when install commands or provider setup
  changes.
- Tell `security` when secrets, prompts, or source documents affect public-safe
  review.

## Do Not

- Make AI dependencies mandatory.
- Commit API keys, private prompts, or internal model endpoints.
- Add provider-specific behavior to core negotiation.
- Teach client-side rendering as the primary streaming path.

## Own

**Code:** `src/chirp/ai/`.
**Tests:** AI provider, streaming, structured output, and missing-extra tests.
**Docs:** AI optional-extra docs/examples and README rows.
**Agent artifacts:** this file.
**CODEOWNERS:** manual-confirmation-needed; no CODEOWNERS file exists.
