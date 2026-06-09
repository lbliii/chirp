CSP nonces now stay live across the Suspense streaming drain. Previously
`CSPNonceMiddleware` reset its nonce `ContextVar` in a `finally` the instant the
handler returned — before any `StreamingResponse` (e.g. `Suspense`) chunk was
produced — so framework-emitted inline scripts (`format_oob_script`) streamed
with a dead/empty nonce. The nonce is now carried on `StreamingResponse` and
re-established in `send_streaming_response` (mirroring the existing
`request_context` lifecycle), and threaded through every framework inline-script
emitter (`format_oob_script`, `alpine_snippet`/`safe_data_helper`,
`alpine_json_config`). As a result the default CSP (both
`SecurityHeadersConfig.content_security_policy` and the production HSTS-path CSP)
drops `'unsafe-inline'` from `script-src`. A new `csp_nonce` contract category
ERRORs when a framework inline script would be un-nonced under an
inline-forbidding CSP (e.g. `alpine=True` under a nonce-only policy without the
`@alpinejs/csp` build). ([#181](https://github.com/lbliii/chirp/issues/181))
