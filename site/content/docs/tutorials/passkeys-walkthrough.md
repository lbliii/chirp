---
title: Passkeys Beside Passwords
description: Enroll and authenticate WebAuthn passkeys with Chirp's ceremony verbs, BYO credential store, window.chirp.passkeys bridge, and app.check() passkeys category
draft: false
weight: 9
lang: en
type: doc
tags: [tutorial, auth, passkeys, webauthn, security, app-check]
keywords: [chirp passkeys, webauthn walkthrough, passkey registration, passkey login, chirp passkeys extra]
category: tutorial
---

## Overview

Passkeys are **one authenticator beside passwords**, not a replacement for your
identity core. Chirp's doctrine matches passwords: the framework owns the
**verb** (the ceremony + the session-bound challenge lifecycle); your app owns
the **row** (credential persistence), exactly like
[[docs/tutorials/auth-login-walkthrough|the password login walkthrough]] owns the
user table but calls `hash_password` / `verify_login`.

This tutorial wires the full loop:

1. **Register** — enroll a credential for an already-identified user (`@login_required`)
2. **Authenticate** — prove possession, then call `login(user)` yourself
3. **Bridge** — `AppConfig(passkeys=True)` injects `window.chirp.passkeys` for the browser ceremony
4. **Startup** — `app.check()` fires the `passkeys` category before you ship

**Prerequisites:** Python 3.14+, the auth stack from the login walkthrough, and
the optional passkeys extra:

```bash
pip install "bengal-chirp[auth,passkeys]"
export CHIRP_SECRET_KEY=$(python -c "import secrets; print(secrets.token_hex(32))")
```

Missing `webauthn` fails **loud** at first ceremony use with a
`ConfigurationError` — there is no stdlib fallback.

## Relying-party config

`PasskeyConfig` validates the WebAuthn footgun at construction: `rp_id` must be
a registrable suffix of every `origin` you accept.

```python
from chirp.security.passkeys import PasskeyConfig

PK = PasskeyConfig(
    rp_id="localhost",
    rp_name="My App",
    origin="http://localhost:8000",  # production: https://app.example.com
)
```

On Railway or any HTTPS deploy, set both env vars to your public hostname — see
`examples/chirpui/lucky_cat/passkey_config.py`.

## BYO credential store

Implement persistence with any object exposing `credential_id`, `public_key`,
`sign_count`, and `user_id` — a dataclass, an ORM row, whatever you already use.
The verbs only read `public_key` and `sign_count` during authentication.

```python
from dataclasses import dataclass
from chirp.security.passkeys import RegisteredCredential

@dataclass(frozen=True, slots=True)
class StoredPasskey:
    credential_id: bytes
    public_key: bytes
    sign_count: int
    user_id: str
```

After `finish_registration`, bind `user_id` and persist the row. After
`finish_authentication`, update `sign_count` **before** calling `login(user)`.

## Ceremony routes

Each ceremony is a **begin → finish** pair. `begin_*` stashes a single-use
challenge in the session and returns JSON for the JS bridge. `finish_*` pops the
challenge before verifying — so `login()` → `regenerate_session()` can never wipe
a not-yet-consumed challenge.

```python
from webauthn.helpers import base64url_to_bytes

from chirp import JSONResponse, Request, current_user, login, login_required
from chirp.security.passkeys import (
    PasskeyVerificationError,
    begin_authentication,
    begin_registration,
    finish_authentication,
    finish_registration,
)

@app.route("/auth/passkey/register/begin", methods=["POST"])
@login_required
async def register_begin():
    user = current_user()
    options = begin_registration(
        user_id=user.id.encode(),
        user_name=user.id,
        user_display_name=user.name,
        exclude_credentials=[...],  # ids the user already enrolled
        config=PK,
    )
    return JSONResponse.from_value(options)

@app.route("/auth/passkey/register/finish", methods=["POST"])
@login_required
async def register_finish(request: Request):
    body = await request.json()
    try:
        registered = finish_registration(credential=body, config=PK)
    except PasskeyVerificationError:
        return JSONResponse.from_value({"error": "Registration failed."}, status=422)
    store.save(current_user().id, registered)
    return JSONResponse.from_value({"ok": True})

@app.route("/auth/passkey/login/begin", methods=["POST"])
async def login_begin():
    return JSONResponse.from_value(begin_authentication(config=PK))

@app.route("/auth/passkey/login/finish", methods=["POST"])
async def login_finish(request: Request):
    body = await request.json()
    stored = store.get(base64url_to_bytes(body["id"]))
    if stored is None:
        return JSONResponse.from_value({"error": "Unknown passkey."}, status=422)
    try:
        verified = finish_authentication(credential=body, stored=stored, config=PK)
    except PasskeyVerificationError:
        return JSONResponse.from_value({"error": "Authentication failed."}, status=422)
    store.update_sign_count(stored.credential_id, verified.new_sign_count)
    login(await load_user(stored.user_id))  # ← single identity-termination point
    return JSONResponse.from_value({"ok": True, "redirect": "/dashboard"})
```

## Browser bridge + CSRF

Enable the bridge in config:

```python
config = AppConfig(..., passkeys=True)
```

Chirp injects `window.chirp.passkeys.register()` / `.authenticate()` before
`</body>`. The JS POST is **not** a template `<form>`, so include the CSRF token
yourself:

```javascript
const csrf = document.querySelector('meta[name="csrf-token"]')?.content;
const opts = await (await fetch('/auth/passkey/login/begin', {
  method: 'POST',
  headers: csrf ? {'X-CSRF-Token': csrf} : {},
})).json();
const credential = await chirp.passkeys.authenticate(opts);
await fetch('/auth/passkey/login/finish', {
  method: 'POST',
  headers: {'Content-Type': 'application/json', ...(csrf ? {'X-CSRF-Token': csrf} : {})},
  body: JSON.stringify(credential),
});
```

Errors thrown by the bridge carry `.passkeyReason` of `cancelled`, `duplicate`,
`misconfigured`, `unsupported`, or `failed`.

## app.check() passkeys category

When `passkeys=True`, startup checks the `webauthn` dependency (see
[[docs/quality/contracts-debugging/categories#passkeys-webauthn-ceremony-posture|passkeys category]]):

| Check | Severity | Fix |
|---|---|---|
| `webauthn` not installed | ERROR (all envs) | `pip install chirp[passkeys]` |

Cookie sessions are first-class for passkeys — the begin → finish challenge is
stored in the session on both `CookieSessionStore` and optional
`RedisSessionStore`. Redis is for shared/horizontal session state, not a
passkeys requirement. Run `chirp check --deploy` before shipping to catch
production-only posture failures elsewhere in the security stack.

## Clone-and-run references

| Example | What it proves |
|---|---|
| `examples/standalone/passkeys_minimal/` | Slim password + passkey reference (#463) |
| `examples/chirpui/lucky_cat/` | Product-shaped login + settings enrollment (#464) |

Browser e2e with a virtual authenticator: `pytest -m passkeys_e2e` on
`passkeys_minimal/test_browser_smoke.py` (#465).

:::{note} See also
- [[docs/tutorials/auth-login-walkthrough|Auth login walkthrough]] — password golden path
- [[docs/about/core-concepts/configuration|Configuration]] — `passkeys` / `passkeys_version` flags
- [[docs/quality/deployment/auth-hardening|Auth hardening]] — production wiring checklist
:::
