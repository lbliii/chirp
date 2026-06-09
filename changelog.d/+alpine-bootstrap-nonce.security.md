Every framework-emitted inline `<script>` now carries the live per-request CSP
nonce, not just Alpine. Each compile-time injection — the Alpine `safeData`
bootstrap, `safe_target`, `sse_lifecycle`, `delegation`, the `view_transitions`
script, the `islands` runtime, and the `speculation_rules`
`<script type="speculationrules">` — is built through a per-request snippet
factory (`nonce -> snippet`) that `HTMLInject` resolves from `csp_nonce()` in
request scope, on both the buffered full-page path and the streaming/Suspense
path. Combined with the Suspense (#181) and SSE (#194) lifecycle fixes, every
framework inline script survives a strict nonce-only CSP when a nonce mechanism
is active (`CSPNonceMiddleware` or `AppConfig(csp_nonce_enabled=True)`), so a
standard `alpine=True` app no longer needs `alpine_csp=True`. View-transitions
HEAD markup is a `<meta>`/`<style>` pair governed by `style-src`, not
`script-src`, so it is left un-nonced by design. The `csp_nonce` contract was a
permanent no-op; it now flags the genuinely un-nonceable case — an
inline-forbidding CSP (a `script-src` without `'unsafe-inline'`) in force with no
per-request nonce mechanism while a framework inline-script feature is enabled —
with env-aware severity (ERROR in production, WARNING in staging, silent in
development), naming the fix (enable `CSPNonceMiddleware`/`csp_nonce_enabled`, or
add `'unsafe-inline'`). ([#195](https://github.com/lbliii/chirp/issues/195))
