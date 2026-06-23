# Passkeys Minimal

Standalone reference for password auth **plus** WebAuthn passkey ceremonies on
Chirp. Clone-and-run sibling to `examples/standalone/auth/`.

## What it shows

- `chirp.security.passkeys` — `PasskeyConfig`, begin/finish verbs, BYO credential store
- `AppConfig(passkeys=True)` — injects `window.chirp.passkeys` for browser ceremonies
- CSRF on JSON finish POSTs via `X-CSRF-Token`
- `login(user)` after `finish_authentication` — same identity path as passwords

## Run

```bash
pip install "bengal-chirp[auth,passkeys]"
export CHIRP_SECRET_KEY=$(python -c "import secrets; print(secrets.token_hex(32))")
PYTHONPATH=src python examples/standalone/passkeys_minimal/app.py
```

Open `http://localhost:8000`. Sign in as **admin / password**, visit **Passkeys** to
enroll, then sign out and use **Sign in with passkey**.

## WebAuthn posture

WebAuthn requires a **registrable-suffix match** between `PasskeyConfig.rp_id` and
`PasskeyConfig.origin`, and **HTTPS** in production (the `cookie_secure` contract
guarantees Secure cookies under production posture).

| Environment | Suggested values |
|---|---|
| Local dev | `PASSKEY_RP_ID=localhost`, `PASSKEY_ORIGIN=http://localhost:8000` |
| Production | `PASSKEY_RP_ID=example.com`, `PASSKEY_ORIGIN=https://app.example.com` |

`app.check()` fires the `passkeys` category when `passkeys=True`: an ERROR if
`webauthn` is missing, and a production/staging WARNING if you use the cookie
session store with passkey-heavy traffic (challenge bloat — prefer Redis).

## Test

```bash
uv run --with 'webauthn>=2.8,<3' pytest examples/standalone/passkeys_minimal/ -q
```

Browser e2e (virtual authenticator) lives in `test_browser_smoke.py` — opt-in
via `pytest -m passkeys_e2e`.

## See also

- [[docs/tutorials/passkeys-walkthrough|Passkeys walkthrough]]
- [[docs/tutorials/auth-login-walkthrough|Auth login walkthrough]] — password golden path
- `examples/chirpui/lucky_cat/` — product-shaped consumer (#464)
