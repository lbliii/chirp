`use_chirp_ui(app)` now owns the "chirp-ui needs a working CSP" fact, so a chirp-ui
app survives secure-by-default with **no hand-written Content-Security-Policy**.
chirp-ui drives its shell with Alpine, which evaluates expressions as JS (needs
`script-src 'unsafe-eval'`) and toggles visibility via inline `style="display:none"`
attributes that **cannot be nonced** (needs `style-src 'unsafe-inline'`). The default
CSP forbids both, which silently killed the entire interactive shell — collapse,
dropdowns, theme toggle, modals, command palette — with no console error (CORS masks
it). `use_chirp_ui` now flips `csp_nonce_enabled=True` in the same `bind_config` that
auto-enables Alpine, so the compiler wires `CSPNonceMiddleware` as the single CSP
authority: a per-request nonce `script-src` plus `'unsafe-eval'`, and a new
`style-src 'self' 'unsafe-inline'` (the irreducible relaxation scoped to style-src
only — script-src stays nonce-only). `CSPNonceMiddleware` gains a public
`style_unsafe_inline: bool` constructor parameter for this; the compiler sets it the
same way it sets `unsafe_eval` (`config.alpine and not config.alpine_csp`). A new
env-aware built-in contract check, category `chirpui_csp`, **fails loud** at
`app.check()` time (ERROR in production, WARNING in staging, silent in development)
when a chirp-ui app's effective CSP would still kill Alpine — e.g. a conflicting
static `SecurityHeadersMiddleware` policy that forbids the inline bootstrap/eval or
inline style — instead of letting the invisible browser failure happen. Non-chirp-ui
apps are unaffected (the check no-ops). The `lucky_cat` example drops its ~20-line
hand-written `_CHIRP_UI_CSP` workaround and relies on the framework, keeping only a
bare `SecurityHeadersMiddleware(content_security_policy=None)` for the
clickjacking/MIME/referrer headers. ([#233](https://github.com/lbliii/chirp/issues/233))
