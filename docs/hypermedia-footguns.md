# Hypermedia Footguns Matrix

Chirp should remove common hypermedia footguns by design where it can, and
name the rest at startup. This matrix tracks the recurring hazards that show
up in examples and apps, plus the framework shape that should make each one
harder to hit.

| Symptom | Cause | Chirp protection | Safe pattern | Canonical example |
| --- | --- | --- | --- | --- |
| An htmx swap inserts a whole page into a small target | Manual htmx branching returns the wrong shape | `Page`, `Fragment`, `MutationResult`, `ValidationError`, and return negotiation | Prefer return types over `if request.is_htmx` branches; branch only when the page truly differs | `examples/standalone/returns_gallery`, `examples/standalone/todo` |
| A streamed answer nests a full page inside an htmx target | `TemplateStream` on a route that an `hx-target` form POSTs to | `template_stream_client_shape` contract warning | Use plain form POST for `TemplateStream`, or `Fragment`/`EventStream` for in-place swaps | `examples/standalone/llm_minimal`, `examples/standalone/llm_streaming_kida` |
| SSE shows only the last token | Per-token Fragments with `hx-swap="innerHTML"` on the `sse-swap` sink | `sse_token_swap_mode` contract warning | Append with `hx-swap="beforeend"` (or `afterend`) for token streams | `examples/standalone/llm_minimal`, `chirp new --stream` |
| SSE starts before the user acts | Static `sse-connect="/…"` on a GET page template | `sse_eager_connect` contract info | POST → `Fragment` with parametric connect; mark intentional feeds | `examples/standalone/sse`, `chirpui/llm_playground` |
| A mutation wipes a broad shell region | Form inherits a layout-level `hx-target` or `hx-swap` | `swap_safety` contract warnings and `safe_region` helpers | Put mutating forms inside a local target or return `Action`/`FormAction` with explicit fragments | `examples/chirpui/contacts_shell` |
| Boosted navigation blanks a shell outlet | A replace-mode or omitted layout owns an inherited `hx-select`, but the page fragment omits the selected id | `layout_outlet` contract error and an htmx 2 `HX-Reselect: *` response backstop | Prefer composed outlets, or include the selected wrapper in the wide page fragment | `tests/contracts/test_shell_outlet_boosted_navigation.py` |
| A literal QUERY client fails before rendering results | Its URL, method, `Content-Type`, route media declaration, or CORS preflight does not agree | `query_target`, `query_method`, `query_media_type`, and `query_cors` contract errors | Keep literal Fetch/`htmx.ajax()` calls aligned with the explicit QUERY route and its normalized media ranges | `tests/contracts/test_query_contracts.py` |
| SSE or OOB updates flicker, disappear, or animate the whole page | Live updates target an element with `transition:true` or `view-transition-name` | `view_transition_scope` contract warnings | Keep broad containers transition-free; put transitions on narrow navigation or detail elements | `examples/standalone/hackernews`, `chirp new --sse` |
| An SSE payload goes nowhere | The SSE scope is inside a boosted content block and gets replaced | `sse_scope` macro and scaffold tests | Put the SSE listener in a persistent layout block, outside boosted content | `src/chirp/cli/templates/sse.py` |
| An OOB swap silently empties a region | Missing block or typo in the target name | `BlockNotFoundError` and OOB contract checks | Register real OOB regions and let missing blocks fail loudly | `examples/standalone/oob_layout_chain` |
| A page works but its block-fetch or htmx fragment route 500s | Fragment block uses a macro or binding imported inside an ancestor block | `fragment_scope` contract warning | Put imports and bindings needed by fragment blocks at template top level, or inside the fragment block itself | `chirp-ui` island remount showcase |
| Suspense resolves to the wrong branch for empty data | Template checks `{% if key %}` after deferred resolution | `defer_falsy` contract warning | Use `{% if key is deferred %}` or `"key" in __chirp_defer_pending__` before testing resolved values | `examples/standalone/suspense_dashboard` |
| Suspense deferred keys cannot resolve independently | Two or more deferred keys share one leaf block (`couples` edge in the freeze-time DAG) | `defer_coupling` contract warning (staging/production; silent in development) | Give each independent defer its own leaf block; keep a shared panel only when serial resolution is intentional | `examples/standalone/suspense_dashboard` |
| CSRF helpers appear present when CSRF is not installed | A template engine default helper masks Chirp's middleware helper | Chirp removes the generic Kida `csrf_token` helper during environment creation | Check `csrf_token is defined` only when using `CSRFMiddleware` | `examples/standalone/upload`, `examples/standalone/signup` |
| A production form works locally but loses fields or bypasses validation at scale | Manual form parsing drifts across repeated fields, submit intents, and htmx/plain fallbacks | `form_from`, `FormContract`, `ValidationError`, and `form_contract` checks | Bind to dataclasses, declare mounted page contracts, and use explicit `intent` fields for multi-intent forms | `examples/chirpui/forum_shell`, `examples/chirpui/contacts_shell` |
| Page templates look like they override layout siblings but do not | A page template extends a registered layout instead of composing into it | `composition_extends` contract warning | Let `Page(..., page_block_name=...)` compose into the layout content slot | `chirp new`, `examples/standalone/oob_layout_chain` |
| Alpine fails with a masked browser error | Bare package CDN URL resolves to the wrong bundle | `alpine_cdn_url` contract error and CDN URL tests | Use explicit `/dist/cdn.min.js` URLs or Chirp's Alpine injection | `examples/standalone/freeze_site` |

## Design Digest

The pattern is consistent: when a bug would corrupt visible HTML, Chirp should
prefer a typed return or a startup contract over documentation alone. Examples
then become executable design notes: standalone examples show raw hypermedia
contracts, and ChirpUI examples show how the same contracts behave inside a
shell and component layer.

## Contract diagnostic author checklist

Every `ERROR` and `WARNING` emitted through `app.check()` is an actionable
contract, not a generic lint observation. Rule authors keep the primary
message precise and short:

- Name the broken subject and the declared surface that owns it.
- State the user-visible or runtime consequence without guessing at a fix.
- Put rule-specific alternatives, discovered values, or locations in `details`.
- Do not include secrets, exception text, private absolute paths, or request data.

The checked-in [diagnostic inventory](contract-diagnostic-inventory.json) is
the audit receipt for every core category, while `chirp check --json` remains
the machine-readable inventory for findings from a particular application.
Both preserve stable severity/category/message identity plus route, template,
and optional detail fields. Add rule-specific repair text only where a message
cannot already name the source, consequence, and next surface to change. Avoid
generic suffixes: they make terminal output harder to use and do not give an
agent a more concrete repair. Static analysis must state its limit when the
result depends on request data or browser behavior.

The audit assigns each emitter an explicit family in its readable JSONL
receipt. The inventory test protects source identity and message-family drift;
it does not claim that a syntax heuristic can decide whether a diagnostic is
useful.
