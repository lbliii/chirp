"""Passkeys minimal — password + WebAuthn ceremony reference.

Demonstrates the full BYO-credential-store loop beside password auth:

* ``PasskeyConfig`` + the four begin/finish verbs from ``chirp.security.passkeys``
* ``AppConfig(passkeys=True)`` for the ``window.chirp.passkeys`` JS bridge
* CSRF on JSON finish POSTs via ``X-CSRF-Token``
* ``login(user)`` as the single identity-termination point after ``finish_authentication``

Run::

    pip install "bengal-chirp[auth,passkeys]"
    PYTHONPATH=src python app.py

WebAuthn requires HTTPS in production and a matching ``rp_id`` / ``origin`` pair.
For local dev, ``http://localhost:8000`` with ``rp_id=localhost`` works in
Chromium. Override with ``PASSKEY_ORIGIN`` / ``PASSKEY_RP_ID`` env vars.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import credential_store
from webauthn.helpers import base64url_to_bytes

from chirp import (
    App,
    AppConfig,
    JSONResponse,
    Redirect,
    Request,
    Template,
    current_user,
    get_user,
    is_safe_url,
    login,
    login_required,
    logout,
)
from chirp.middleware.auth import AuthConfig, AuthMiddleware
from chirp.middleware.csrf import CSRFConfig, CSRFMiddleware
from chirp.middleware.security_headers import SecurityHeadersConfig, SecurityHeadersMiddleware
from chirp.middleware.sessions import SessionConfig, SessionMiddleware
from chirp.security.passkeys import PasskeyConfig
from chirp.security.passwords import hash_password, verify_login

TEMPLATES_DIR = Path(__file__).parent / "templates"

_ORIGIN = os.environ.get("PASSKEY_ORIGIN", "http://localhost:8000")
_RP_ID = os.environ.get("PASSKEY_RP_ID", "localhost")
PK = PasskeyConfig(rp_id=_RP_ID, rp_name="Passkeys Minimal", origin=_ORIGIN)


@dataclass(frozen=True, slots=True)
class User:
    id: str
    name: str
    password_hash: str
    is_authenticated: bool = True


_DEMO_HASH = hash_password("password")
USERS: dict[str, User] = {
    "admin": User(id="admin", name="Admin", password_hash=_DEMO_HASH),
}


async def load_user(user_id: str) -> User | None:
    return USERS.get(user_id)


config = AppConfig(template_dir=TEMPLATES_DIR, passkeys=True)
app = App(config=config)

_secret = os.environ.get("CHIRP_SECRET_KEY", "dev-only-not-for-production")

app.add_middleware(SessionMiddleware(SessionConfig(secret_key=_secret)))
app.add_middleware(AuthMiddleware(AuthConfig(load_user=load_user)))
app.add_middleware(CSRFMiddleware(CSRFConfig()))
app.add_middleware(SecurityHeadersMiddleware(SecurityHeadersConfig(content_security_policy=None)))


def _safe_next(raw: str | None) -> str:
    candidate = (raw or "").strip()
    return candidate if candidate and is_safe_url(candidate) else "/dashboard"


@app.route("/")
def index():
    return Template("index.html")


@app.route("/login")
def login_page():
    return Template("login.html", error="")


@app.route("/login", methods=["POST"])
async def do_login(request: Request):
    form = await request.form()
    username = form.get("username", "")
    password = form.get("password", "")

    user = USERS.get(username)
    if verify_login(password, user.password_hash if user else None):
        login(user)
        next_url = request.query.get("next", "/dashboard")
        if not is_safe_url(next_url):
            next_url = "/dashboard"
        return Redirect(next_url)

    return Template("login.html", error="Invalid username or password")


@app.route("/dashboard")
@login_required
def dashboard():
    return Template(
        "dashboard.html", user=get_user(), passkeys=credential_store.list_for_user(get_user().id)
    )


@app.route("/passkeys")
@login_required
def passkeys_page():
    return Template("passkeys.html", passkeys=credential_store.list_for_user(get_user().id))


@app.route("/auth/passkey/register/begin", methods=["POST"])
@login_required
async def passkey_register_begin():
    from chirp.security.passkeys import begin_registration

    user = current_user()
    existing = [row.credential_id for row in credential_store.list_for_user(user.id)]
    options = begin_registration(
        user_id=user.id.encode(),
        user_name=user.id,
        user_display_name=user.name,
        exclude_credentials=existing,
        config=PK,
    )
    return JSONResponse.from_value(options)


@app.route("/auth/passkey/register/finish", methods=["POST"])
@login_required
async def passkey_register_finish(request: Request):
    from chirp.security.passkeys import PasskeyVerificationError, finish_registration

    user = current_user()
    body = await request.json()
    try:
        registered = finish_registration(credential=body, config=PK)
    except PasskeyVerificationError:
        return JSONResponse.from_value({"error": "Registration failed."}, status=422)
    credential_store.save(user.id, registered)
    return JSONResponse.from_value({"ok": True, "redirect": "/passkeys"})


@app.route("/auth/passkey/login/begin", methods=["POST"])
async def passkey_login_begin():
    from chirp.security.passkeys import begin_authentication

    options = begin_authentication(config=PK)
    return JSONResponse.from_value(options)


@app.route("/auth/passkey/login/finish", methods=["POST"])
async def passkey_login_finish(request: Request):
    from chirp.security.passkeys import PasskeyVerificationError, finish_authentication

    body = await request.json()
    cred_id = body.get("id") if isinstance(body, dict) else None
    if not isinstance(cred_id, str) or not cred_id:
        return JSONResponse.from_value({"error": "Missing credential id."}, status=422)

    stored = credential_store.get(base64url_to_bytes(cred_id))
    if stored is None:
        return JSONResponse.from_value({"error": "Unknown passkey."}, status=422)

    try:
        verified = finish_authentication(credential=body, stored=stored, config=PK)
    except PasskeyVerificationError:
        return JSONResponse.from_value({"error": "Authentication failed."}, status=422)

    credential_store.update_sign_count(stored.credential_id, verified.new_sign_count)
    user = await load_user(stored.user_id)
    if user is None:
        return JSONResponse.from_value({"error": "Unknown user."}, status=422)

    login(user)
    next_url = _safe_next(body.get("next") if isinstance(body, dict) else None)
    return JSONResponse.from_value({"ok": True, "redirect": next_url})


@app.route("/logout", methods=["POST"])
def do_logout():
    logout()
    return Redirect("/")


if __name__ == "__main__":
    app.run()
