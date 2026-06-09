The `chirp new` chirp-ui scaffold no longer ships a CSP posture that silently
breaks Alpine. It previously set `alpine_csp=True` to satisfy the `csp_nonce`
contract after `'unsafe-inline'` was dropped from the default CSP, but the
`@alpinejs/csp` build forbids the inline Alpine expressions chirp-ui components
rely on (modal `x-data` factory calls, dropdown/sidebar/tray inline
`@click`/`x-show`/`:class`), so those components died in the browser (CORS masks
the error). The scaffold now runs the normal Alpine build under a per-request
nonce CSP via `csp_nonce_enabled=True`, which auto-wires `CSPNonceMiddleware`
(with `'unsafe-eval'` for Alpine) — keeping the `csp_nonce` contract clean while
chirp-ui interactivity actually works. ([#196](https://github.com/lbliii/chirp/issues/196))
