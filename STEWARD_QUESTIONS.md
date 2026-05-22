# Steward Questions

These questions capture design intent the bootstrap could not safely infer from
source, tests, docs, changelog, or PR history. Treat every answer as
manual-confirmation-needed until a follow-up PR records it in code, docs, tests,
or steward guidance.

## Root Constitution

- Which human review routing should replace the current no-CODEOWNERS
  `manual-confirmation-needed` status?
- Which cross-repo conflicts should escalate outside this repository, and to
  whom?
- Should the Convergence Rule apply to all severities or only accepted P0/P1
  findings?

## Public Surface

- Which provisional top-level exports are likely to stabilize before 1.0?
- Are any current `AppConfig` fields accidental implementation details that
  should move before 1.0?
- What deprecation window should stable names receive before removal?

## App Lifecycle

- Is `mount_app()` intended as a long-term public pattern or only a migration
  bridge?
- Which lifecycle errors are stable enough for app code to catch by message or
  type?
- Should third-party plugins receive a richer freeze/runtime hook contract?

## HTTP Primitives

- Which HTTP collection behaviors are compatibility promises versus internal
  conveniences?
- Should `JSONResponse` remain stable for progressive-enhancement data islands
  only, or is a broader JSON story planned?
- What performance budget should protect `SyncRequest` changes?

## Routing

- Which path converters are part of the 1.0 compatibility promise?
- Should route shadowing become an `app.check()` error or remain advisory?
- How should mounted route-name collisions be resolved for long-term plugin
  ecosystems?

## Protocol And Negotiation

- Which parts of negotiation dispatch order are intentionally stable?
- What parity budget should sync handling meet before sync-path changes merge?
- Should DevTools diagnostics become a documented public debugging API?

## Rendering

- Which render-plan types are debug-only forever versus candidates for public
  extension APIs?
- Should optional OOB regions remain warning-level, or should context decide
  severity?
- What Kida upgrade policy should govern render-pipeline compatibility claims?

## Contract Checks

- Which contract categories are public compatibility promises before 1.0?
- What is the acceptable false-positive rate for startup warnings?
- Should custom checker exceptions always become `ERROR`, or can some be
  isolated as `INFO`?

## Filesystem Pages And Shell

- Which route-directory conventions are stable versus experimental?
- Should shell actions/regions become independent of ChirpUI long term?
- What reactive-page API shape is intended for 1.0, if any?

## Middleware Pipeline

- Which middleware orderings should `app.check()` enforce by default?
- Should built-in security middleware become auto-enabled in more production
  modes?
- What lifecycle should bound rate-limit and lockout in-memory state?

## Security Primitives

- Which helpers are stable primitives versus examples of one possible auth
  policy?
- Should safe URL validation support tenant/base-path rules as first-class
  config?
- What audit event schema stability is promised to external sinks?

## Cache

- Which request/response inputs are mandatory cache-key components for 1.0?
- Should cache middleware expose introspection headers in debug mode?
- What Redis behavior is compatibility-relevant versus backend detail?

## Data And Schema

- Is the data package intended to remain a helper layer, or grow toward a
  supported persistence story?
- What migration rollback story, if any, should be documented?
- Which query-builder methods are stable enough for public docs?

## Realtime

- Which SSE error events should be observable by clients versus logs only?
- Should EventStream reconnect/retry policy be configurable per stream or app?
- What long-lived stream cleanup guarantees are intended for user generators?

## Validation

- Which validation rules are stable API versus examples of common rules?
- Should validation support localization through `chirp.i18n`?
- What error message shape should form-rendering examples standardize on?

## CLI And Scaffolds

- Which scaffold variants should be treated as compatibility surfaces?
- Should `chirp freeze` output format be stable enough for downstream tooling?
- What CLI command additions require release-policy or migration notes?

## Testing Helpers

- Which testing assertions are stable public helper API?
- Should helpers expose render-plan/debug metadata to app tests?
- What minimum browser/htmx realism should `TestClient` simulate?

## Docs Tooling

- Which docs plugin models are public compatibility surfaces?
- Should docs search output schema be stable for external consumers?
- How should autodoc mark generated versus manually authored content?

## Markdown Optional Extra

- What sanitization/security posture should Markdown rendering document?
- Which renderer options should become public before 1.0?
- Should Markdown filters integrate with docs tooling or remain independent?

## i18n Optional Surface

- Is i18n intended for 1.0 stabilization or post-1.0 experimentation?
- What fallback policy should missing translations follow?
- Should locale detection support URL prefixes, cookies, and headers equally?

## AI Optional Extra

- Which provider abstractions should be stable versus experimental?
- Should AI streaming helpers standardize on fragments, SSE, or both?
- What public-safe example policy should govern prompts and sources?

## Extension Adapters

- Is `chirp-ui` the only planned first-party extension adapter?
- Which extension readiness states should contracts validate by default?
- Should strict extension behavior be app-level, environment-level, or per
  adapter?

## MCP Tools

- Which MCP/tool schema fields are stable enough for external clients?
- Should tool execution events be persisted, streamed, or only in-memory?
- What security model should tool exposure document for production apps?

## Test Suite

- Which test categories must pass before release-class PRs merge?
- What is the policy for slow/integration tests in default CI?
- Should regression tests include PR/commit references in comments or names?

## Contract Tests

- Which contract categories require end-to-end coverage before new rules ship?
- What level of message wording should tests freeze?
- Should contract coverage counters become release-gated metrics?

## Examples

- Which examples are canonical enough to block release when failing?
- Should examples track multiple install modes such as core, full, and optional
  extras?
- What design standard should examples follow when plain CSS diverges from
  ChirpUI examples?

## Narrative Docs

- Which docs are canonical when README, docs, and site content disagree?
- Should old planning docs be archived, marked superseded, or kept as context?
- What product story should guide docs as 1.0 approaches?

## Bengal Docs Site

- Should generated `site/public/` be committed as release output or ignored
  unless explicitly requested?
- Which site config changes require screenshots or build artifacts?
- What source controls release page content: `CHANGELOG.md`, `site/content`, or
  release readiness docs?

## Benchmarks

- What benchmark delta should block release or require investigation?
- Which benchmark environments are canonical for release notes?
- Should benchmark JSON output be treated as a stable artifact schema?

## Changelog Fragments

- Which PR types can skip a changelog fragment?
- Should dependency-only changes use `changed`, `fixed`, or a dedicated type?
- What level of migration detail belongs in fragments versus release notes?

## Planning And Roadmap

- Who decides when a draft plan becomes accepted?
- What artifacts should record rejected steward findings?
- How often should completed plans be pruned, archived, or linked from roadmap?
