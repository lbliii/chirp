"""Passkey ceremony routes — register (settings) + authenticate (login)."""

from __future__ import annotations

import passkey_config
import passkey_store
import users

from chirp import JSONResponse, Request, current_user, is_safe_url, login, login_required
from webauthn.helpers import base64url_to_bytes


def _safe_next(raw: str | None) -> str:
    candidate = (raw or "").strip()
    return candidate if candidate and is_safe_url(candidate) else "/"


def register(app_instance) -> None:
    @app_instance.route("/auth/passkey/register/begin", methods=["POST"])
    @login_required
    async def passkey_register_begin():
        from chirp.security.passkeys import begin_registration

        user = current_user()
        existing = [row.credential_id for row in passkey_store.list_for_user(user.id)]
        options = begin_registration(
            user_id=user.id.encode(),
            user_name=user.id,
            user_display_name=user.name,
            exclude_credentials=existing,
            config=passkey_config.PASSKEY_CONFIG,
        )
        return JSONResponse.from_value(options)

    @app_instance.route("/auth/passkey/register/finish", methods=["POST"])
    @login_required
    async def passkey_register_finish(request: Request):
        from chirp.security.passkeys import PasskeyVerificationError, finish_registration

        user = current_user()
        body = await request.json()
        try:
            registered = finish_registration(credential=body, config=passkey_config.PASSKEY_CONFIG)
        except PasskeyVerificationError:
            return JSONResponse.from_value({"error": "Registration failed."}, status=422)
        passkey_store.save(user.id, registered)
        return JSONResponse.from_value({"ok": True, "redirect": "/settings/security"})

    @app_instance.route("/auth/passkey/login/begin", methods=["POST"])
    async def passkey_login_begin():
        from chirp.security.passkeys import begin_authentication

        allow = passkey_store.all_credential_ids()
        options = begin_authentication(
            allow_credentials=allow or None,
            config=passkey_config.PASSKEY_CONFIG,
        )
        return JSONResponse.from_value(options)

    @app_instance.route("/auth/passkey/login/finish", methods=["POST"])
    async def passkey_login_finish(request: Request):
        from chirp.security.passkeys import PasskeyVerificationError, finish_authentication

        body = await request.json()
        cred_id = body.get("id") if isinstance(body, dict) else None
        if not isinstance(cred_id, str) or not cred_id:
            return JSONResponse.from_value({"error": "Missing credential id."}, status=422)

        stored = passkey_store.get(base64url_to_bytes(cred_id))
        if stored is None:
            return JSONResponse.from_value({"error": "Unknown passkey."}, status=422)

        try:
            verified = finish_authentication(
                credential=body,
                stored=stored,
                config=passkey_config.PASSKEY_CONFIG,
            )
        except PasskeyVerificationError:
            return JSONResponse.from_value({"error": "Authentication failed."}, status=422)

        passkey_store.update_sign_count(stored.credential_id, verified.new_sign_count)
        user = users.get(stored.user_id)
        if user is None:
            return JSONResponse.from_value({"error": "Unknown user."}, status=422)

        login(user)
        next_url = _safe_next(body.get("next") if isinstance(body, dict) else None)
        return JSONResponse.from_value({"ok": True, "redirect": next_url})
