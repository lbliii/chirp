"""WebAuthn / passkey ceremony codec — thin wrappers over ``py_webauthn``.

Requires the optional ``webauthn`` dependency::

    pip install chirp[passkeys]

Chirp owns the **verb** (the ceremony + the session-bound challenge lifecycle);
the app owns the **row** (credential persistence), exactly as
:func:`chirp.security.hash_password` / :func:`~chirp.security.verify_password`
own the hashing verb but not the user table, and as the ``User`` protocol means
the app brings its own user model. Passkeys are one authenticator among several;
they slot beside passwords, they do not replace the identity core.

Each ceremony is a **begin → finish** pair. ``begin_*`` mints a challenge,
stashes it single-use in the session, and returns an options ``dict`` ready for
:class:`chirp.http.response.JSONResponse`. ``finish_*`` pops the challenge,
verifies the authenticator's response, and returns a plain DTO the app
persists::

    from chirp.security.passkeys import (
        PasskeyConfig, begin_registration, finish_registration,
        begin_authentication, finish_authentication,
    )

    PK = PasskeyConfig(rp_id="example.com", rp_name="Example",
                       origin="https://example.com")

    # registration (enroll a credential for an already-identified user)
    @app.route("/auth/passkey/register/begin", methods=["POST"])
    @login_required
    async def register_begin(request):
        u = current_user()
        return JSONResponse.from_value(
            begin_registration(user_id=u.id.encode(), user_name=u.email, config=PK)
        )

    @app.route("/auth/passkey/register/finish", methods=["POST"])
    @login_required
    async def register_finish(request):
        cred = finish_registration(credential=await request.json(), config=PK)
        await store.save_credential(cred, user_id=current_user().id)   # app owns the row
        return FormAction("/settings/passkeys")

    # authentication (prove possession → the handler then calls login(user))
    @app.route("/auth/passkey/login/finish", methods=["POST"])
    async def login_finish(request):
        body = await request.json()
        stored = await store.load_credential(base64url_to_bytes(body["id"]))
        if stored is None:
            return ValidationError("login.html", "passkey_form",
                                   errors={"passkey": "Unknown credential"})
        verified = finish_authentication(credential=body, stored=stored, config=PK)
        await store.update_sign_count(stored.credential_id, verified.new_sign_count)
        login(await load_user(stored.user_id))   # ← single identity-termination point
        return FormAction("/dashboard")

**Ordering is enforced by the verb, not by app discipline.** ``finish_*``
consumes (pops) the challenge *before* it verifies, and it never calls
``login()``. The handler calls ``login()`` only after ``finish_*`` returns — so
``login()`` → ``regenerate_session()`` (which ``session.clear()``s the dict) can
never wipe a not-yet-consumed challenge. The challenge is single-use (popped on
both success and failure) and carries an embedded expiry (the session layer has
no per-key TTL of its own).

Verification is **fail-closed**: ``py_webauthn``'s ``verify_*`` raise on any
mismatch (they never return a falsy result). The verbs catch ``WebAuthnException``
broadly at the boundary and re-raise a generic :class:`PasskeyVerificationError`,
so the route never leaks *which* specific check failed to the client.
"""

from __future__ import annotations

import base64
import binascii
import importlib.util
import json
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable
from urllib.parse import urlparse

from chirp.errors import ChirpError, ConfigurationError

if TYPE_CHECKING:
    from types import ModuleType


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class PasskeyError(ChirpError):
    """Base for passkey ceremony failures."""


class PasskeyChallengeError(PasskeyError):
    """No usable challenge was found for a finish ceremony.

    The challenge was missing, expired, or already consumed (replay). Surface a
    generic "please try again" to the client — never the specific cause.
    """


class PasskeyVerificationError(PasskeyError):
    """An authenticator response failed verification.

    Wraps any ``webauthn.helpers.exceptions.WebAuthnException`` so the route
    handler catches one type and surfaces a generic auth failure. The original
    exception is intentionally suppressed (``from None``) so the specific failed
    check does not leak to the caller / client.
    """


# ---------------------------------------------------------------------------
# Optional-dependency guard (no stdlib fallback — fail loud, like the session
# stores' construction-time ConfigurationError, unlike argon2→scrypt)
# ---------------------------------------------------------------------------


def _has_webauthn() -> bool:
    """Return ``True`` if the optional ``webauthn`` package is importable.

    Used by the ``passkeys`` startup contract check (``rules_passkeys``) — the
    same find-spec probe the runtime uses, so the check and the runtime agree.
    """
    return importlib.util.find_spec("webauthn") is not None


def _require_webauthn() -> ModuleType:
    """Import ``webauthn`` lazily, or fail loud with an actionable message.

    Imported inside the verb functions (never at module top level) so
    ``import chirp`` / ``import chirp.security.passkeys`` never pulls in
    ``webauthn`` (and its ``cryptography`` chain). There is no stdlib WebAuthn
    fallback, so a missing dependency raises ``ConfigurationError`` at first use
    rather than degrading silently — the same fail-loud shape as
    ``CookieSessionStore.__init__`` / ``RedisSessionStore.__init__``.
    """
    try:
        import webauthn
    except ImportError:
        msg = (
            "Passkey support requires the 'webauthn' package. "
            "Install it with: pip install chirp[passkeys]"
        )
        raise ConfigurationError(msg) from None
    return webauthn


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

_USER_VERIFICATION = frozenset({"required", "preferred", "discouraged"})
_RESIDENT_KEY = frozenset({"discouraged", "preferred", "required"})
_ATTESTATION = frozenset({"none", "indirect", "direct", "enterprise"})


@dataclass(frozen=True, slots=True)
class PasskeyConfig:
    """Relying-party configuration for the WebAuthn ceremonies.

    Static, serializable data — constructible without ``webauthn`` installed (so
    the startup contract can inspect it). Misconfiguration fails loud at
    construction; the ``passkeys`` contract check additionally surfaces the
    secure-context / rp_id-suffix posture at startup.

    Args:
        rp_id: The Relying Party ID — a registrable suffix of ``origin`` (e.g.
            ``"example.com"`` for ``https://app.example.com``). It is stamped
            into every credential and **cannot be changed without re-registering
            every user**, so get it right up front.
        rp_name: Human-readable RP name shown by the authenticator UI.
        origin: The full origin(s) the ceremony is bound to, scheme+host+port
            (e.g. ``"https://app.example.com"``). A tuple permits multiple
            accepted origins.
        user_verification: ``required`` | ``preferred`` | ``discouraged``.
            ``required`` forces biometric/PIN and rejects ceremonies where the
            UV flag is unset (true single-factor passwordless).
        resident_key: ``discouraged`` | ``preferred`` | ``required``. ``required``
            forces a discoverable (resident) credential — needed for usernameless
            login + conditional UI, but excludes some authenticators. Default
            ``"preferred"`` serves both username-first and usernameless flows.
        attestation: ``none`` | ``indirect`` | ``direct`` | ``enterprise``.
            ``"none"`` is the correct consumer default.
        timeout: Ceremony timeout in milliseconds, surfaced to the browser.
        challenge_ttl_seconds: Server-side single-use challenge lifetime. The
            session has no per-key TTL, so this is enforced by an embedded
            expiry checked on finish.
    """

    rp_id: str
    rp_name: str
    origin: str | tuple[str, ...]
    user_verification: str = "preferred"
    resident_key: str = "preferred"
    attestation: str = "none"
    timeout: int = 60000
    challenge_ttl_seconds: int = 300

    def __post_init__(self) -> None:
        if not self.rp_id:
            raise ConfigurationError("PasskeyConfig.rp_id must not be empty.")
        if not self.rp_name:
            raise ConfigurationError("PasskeyConfig.rp_name must not be empty.")
        if not self.origin:
            raise ConfigurationError("PasskeyConfig.origin must not be empty.")
        if self.user_verification not in _USER_VERIFICATION:
            raise ConfigurationError(
                f"PasskeyConfig.user_verification must be one of "
                f"{sorted(_USER_VERIFICATION)}, got {self.user_verification!r}."
            )
        if self.resident_key not in _RESIDENT_KEY:
            raise ConfigurationError(
                f"PasskeyConfig.resident_key must be one of "
                f"{sorted(_RESIDENT_KEY)}, got {self.resident_key!r}."
            )
        if self.attestation not in _ATTESTATION:
            raise ConfigurationError(
                f"PasskeyConfig.attestation must be one of "
                f"{sorted(_ATTESTATION)}, got {self.attestation!r}."
            )
        if self.challenge_ttl_seconds <= 0:
            raise ConfigurationError(
                "PasskeyConfig.challenge_ttl_seconds must be a positive number of seconds."
            )
        self._validate_rp_id_origin()

    def _validate_rp_id_origin(self) -> None:
        """Fail loud if ``rp_id`` is not a registrable suffix of every ``origin``.

        A wrong ``rp_id`` is the WebAuthn footgun that throws an opaque
        ``SecurityError`` in the browser and *cannot be migrated without
        re-registering every user* — so it must fail at construction, not at
        runtime. This is the static half of the §9 posture (the HTTPS-in-prod
        half is covered by the ``cookie_secure`` contract, which guarantees a
        Secure cookie — hence HTTPS — under production posture).
        """
        origins = self.origin if isinstance(self.origin, tuple) else (self.origin,)
        for origin in origins:
            host = urlparse(origin).hostname
            if not host:
                raise ConfigurationError(
                    f"PasskeyConfig.origin {origin!r} is not a full origin "
                    "(expected scheme+host, e.g. 'https://app.example.com')."
                )
            if host != self.rp_id and not host.endswith("." + self.rp_id):
                raise ConfigurationError(
                    f"PasskeyConfig.rp_id {self.rp_id!r} is not a registrable suffix of "
                    f"origin host {host!r}. WebAuthn requires rp_id to equal the origin "
                    "host or be a parent domain of it (e.g. rp_id='example.com' for "
                    "origin 'https://app.example.com'). A wrong rp_id breaks every "
                    "ceremony with an opaque browser SecurityError."
                )

    @property
    def expected_origin(self) -> str | list[str]:
        """The origin(s) in the ``str | list[str]`` shape ``py_webauthn`` expects."""
        if isinstance(self.origin, tuple):
            return list(self.origin)
        return self.origin

    @property
    def require_user_verification(self) -> bool:
        """Whether a finish ceremony must reject responses with the UV flag unset."""
        return self.user_verification == "required"


# ---------------------------------------------------------------------------
# Store shape (BYO — the app owns the row, like the User protocol)
# ---------------------------------------------------------------------------


@runtime_checkable
class PasskeyCredential(Protocol):
    """The shape a stored credential must expose for authentication.

    The framework defines the shape; the app owns persistence (a row, an ORM
    model, a dataclass — anything with these attributes). The verbs only read
    ``public_key`` and ``sign_count``; ``credential_id`` is the app's primary
    lookup key and ``user_id`` the link to the app's user.

    Recommended additional columns the app should store but the framework does
    not require: ``transports``, ``aaguid``, ``backup_eligible`` /
    ``backup_state`` (from ``credential_device_type`` / ``credential_backed_up``),
    ``nickname``, ``last_used_at``.
    """

    credential_id: bytes
    public_key: bytes
    sign_count: int
    user_id: Any


@dataclass(frozen=True, slots=True)
class RegisteredCredential:
    """The verified result of a registration ceremony, for the app to persist.

    Bind ``user_id`` yourself when you store it (registration enrolls a
    credential for the user the handler already identified — it does not
    authenticate one).
    """

    credential_id: bytes
    public_key: bytes
    sign_count: int
    aaguid: str
    fmt: str
    credential_device_type: str
    credential_backed_up: bool
    user_verified: bool
    transports: tuple[str, ...] | None = None


@dataclass(frozen=True, slots=True)
class AuthenticatedCredential:
    """The verified result of an authentication ceremony.

    Persist ``new_sign_count`` against the stored credential **before** calling
    ``login()``. ``sign_count_regressed`` is the clone-detection *signal* — the
    framework computes it; the *response* (lock, force re-auth, flag) is app
    policy. Note most synced passkeys (iCloud Keychain, Google) always report a
    sign count of 0, so this is a no-op for them and must not be relied on alone.
    """

    credential_id: bytes
    new_sign_count: int
    user_verified: bool
    credential_device_type: str
    credential_backed_up: bool
    sign_count_regressed: bool


# ---------------------------------------------------------------------------
# Session-backed challenge lifecycle (single-use, embedded TTL, pop-before-login)
# ---------------------------------------------------------------------------

#: Session key holding the in-flight ceremony challenge. ``__``-prefixed so
#: RedisSessionStore strips it from durable storage (it is request-scoped
#: scratch, not user data); the cookie store keeps it (a ~86-char b64url string)
#: only until the matching finish pops it.
CHALLENGE_SESSION_KEY = "__passkey_challenge"


def _b64u_encode(data: bytes) -> str:
    """Encode bytes as unpadded base64url (JSON-safe for the session serializer)."""
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64u_decode(data: str) -> bytes:
    """Decode unpadded base64url back to bytes."""
    pad = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + pad)


def _stash_challenge(challenge: bytes, *, ttl: int) -> None:
    """Store the challenge single-use in the session with an embedded deadline.

    Raises ``LookupError`` if no ``SessionMiddleware`` is active — passkeys
    require the secure-by-default stack, so this fails loud rather than silently
    issuing an unverifiable ceremony.
    """
    from chirp.middleware.sessions import get_session

    get_session()[CHALLENGE_SESSION_KEY] = {
        "c": _b64u_encode(challenge),
        "exp": time.time() + ttl,
    }


def _pop_challenge() -> bytes | None:
    """Pop the stored challenge, returning it only if present and unexpired.

    Always removes the key (single-use, even on expiry/corruption) to defeat
    replay. Returns ``None`` for a missing, expired, or malformed entry — the
    caller raises :class:`PasskeyChallengeError`.
    """
    from chirp.middleware.sessions import get_session

    entry = get_session().pop(CHALLENGE_SESSION_KEY, None)
    if not isinstance(entry, dict):
        return None
    exp = entry.get("exp")
    if not isinstance(exp, (int, float)) or time.time() > exp:
        return None
    encoded = entry.get("c")
    if not isinstance(encoded, str):
        return None
    try:
        return _b64u_decode(encoded)
    except ValueError, binascii.Error:
        return None


def _consume_challenge() -> bytes:
    challenge = _pop_challenge()
    if challenge is None:
        raise PasskeyChallengeError(
            "No valid passkey challenge — it was missing, expired, or already used. "
            "Start the ceremony again."
        )
    return challenge


def _extract_transports(credential: str | dict[str, Any]) -> tuple[str, ...] | None:
    """Best-effort pull of authenticator transports from the client credential.

    Transports live in the client response (``response.transports``), not in the
    verified registration result, so the app should store them to scope future
    ``allow_credentials``. Returns ``None`` when absent/unparseable.
    """
    data: Any = credential
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except ValueError:
            return None
    if not isinstance(data, dict):
        return None
    response = data.get("response")
    if not isinstance(response, dict):
        return None
    transports = response.get("transports")
    if isinstance(transports, list) and all(isinstance(t, str) for t in transports):
        return tuple(transports)
    return None


# ---------------------------------------------------------------------------
# Verbs (wrap py_webauthn 1:1, own the challenge + config plumbing)
# ---------------------------------------------------------------------------


def begin_registration(
    *,
    user_id: bytes,
    user_name: str,
    user_display_name: str | None = None,
    exclude_credentials: list[bytes] | None = None,
    config: PasskeyConfig,
) -> dict[str, Any]:
    """Mint registration options, stash the challenge, return options JSON.

    Args:
        user_id: Opaque per-user handle as bytes (encode your user id, e.g.
            ``user.id.encode()``). Stamped into the credential; not the username.
        user_name: The account identifier the authenticator displays (email/handle).
        user_display_name: Friendly name; defaults to ``user_name``.
        exclude_credentials: Raw ``credential_id`` bytes the user has already
            registered, so the authenticator refuses to re-enroll the same key.
        config: The relying-party config.

    Returns:
        A ``dict`` (camelCase, base64url'd bytes) ready for
        ``JSONResponse.from_value`` and the JS bridge's ``register()``.
    """
    webauthn = _require_webauthn()
    from webauthn.helpers import options_to_json_dict
    from webauthn.helpers.structs import (
        AttestationConveyancePreference,
        AuthenticatorSelectionCriteria,
        PublicKeyCredentialDescriptor,
        ResidentKeyRequirement,
        UserVerificationRequirement,
    )

    selection = AuthenticatorSelectionCriteria(
        resident_key=ResidentKeyRequirement(config.resident_key),
        user_verification=UserVerificationRequirement(config.user_verification),
    )
    options = webauthn.generate_registration_options(
        rp_id=config.rp_id,
        rp_name=config.rp_name,
        user_name=user_name,
        user_id=user_id,
        user_display_name=user_display_name or user_name,
        attestation=AttestationConveyancePreference(config.attestation),
        authenticator_selection=selection,
        exclude_credentials=[
            PublicKeyCredentialDescriptor(id=cid) for cid in (exclude_credentials or [])
        ],
        timeout=config.timeout,
    )
    _stash_challenge(options.challenge, ttl=config.challenge_ttl_seconds)
    return options_to_json_dict(options)


def finish_registration(
    *,
    credential: str | dict[str, Any],
    config: PasskeyConfig,
    require_user_verification: bool | None = None,
) -> RegisteredCredential:
    """Pop the challenge, verify the attestation, return a credential to persist.

    Args:
        credential: The client's registration response (the JS bridge's POST
            envelope — a JSON string or already-parsed dict).
        config: The relying-party config.
        require_user_verification: Override the UV requirement; defaults to
            ``config.require_user_verification``.

    Raises:
        PasskeyChallengeError: No valid challenge (missing/expired/replayed).
        PasskeyVerificationError: The attestation failed any check.

    Returns:
        A :class:`RegisteredCredential` — bind ``user_id`` and persist it.
    """
    webauthn = _require_webauthn()
    from webauthn.helpers.exceptions import WebAuthnException

    challenge = _consume_challenge()
    ruv = (
        config.require_user_verification
        if require_user_verification is None
        else require_user_verification
    )
    try:
        verified = webauthn.verify_registration_response(
            credential=credential,
            expected_challenge=challenge,
            expected_rp_id=config.rp_id,
            expected_origin=config.expected_origin,
            require_user_verification=ruv,
        )
    except WebAuthnException:
        raise PasskeyVerificationError("Passkey registration could not be verified.") from None

    return RegisteredCredential(
        credential_id=verified.credential_id,
        public_key=verified.credential_public_key,
        sign_count=verified.sign_count,
        aaguid=str(verified.aaguid),
        fmt=str(verified.fmt),
        credential_device_type=str(verified.credential_device_type),
        credential_backed_up=bool(verified.credential_backed_up),
        user_verified=bool(verified.user_verified),
        transports=_extract_transports(credential),
    )


def begin_authentication(
    *,
    allow_credentials: list[bytes] | None = None,
    config: PasskeyConfig,
) -> dict[str, Any]:
    """Mint authentication options, stash the challenge, return options JSON.

    Args:
        allow_credentials: Raw ``credential_id`` bytes to restrict the ceremony
            to (username-first login). Omit / empty for usernameless
            (discoverable-credential) login.
        config: The relying-party config.

    Returns:
        A ``dict`` ready for ``JSONResponse.from_value`` and the JS bridge's
        ``authenticate()``.
    """
    webauthn = _require_webauthn()
    from webauthn.helpers import options_to_json_dict
    from webauthn.helpers.structs import (
        PublicKeyCredentialDescriptor,
        UserVerificationRequirement,
    )

    descriptors = [PublicKeyCredentialDescriptor(id=cid) for cid in (allow_credentials or [])]
    options = webauthn.generate_authentication_options(
        rp_id=config.rp_id,
        timeout=config.timeout,
        user_verification=UserVerificationRequirement(config.user_verification),
        allow_credentials=descriptors or None,
    )
    _stash_challenge(options.challenge, ttl=config.challenge_ttl_seconds)
    return options_to_json_dict(options)


def finish_authentication(
    *,
    credential: str | dict[str, Any],
    stored: PasskeyCredential,
    config: PasskeyConfig,
    require_user_verification: bool | None = None,
) -> AuthenticatedCredential:
    """Pop the challenge, verify the assertion against the stored credential.

    Does **not** call ``login()`` — the handler persists ``new_sign_count`` and
    then calls ``login(user)`` (the single identity-termination point). Consuming
    the challenge here, before the handler's ``login()``, is what keeps
    ``regenerate_session()`` from wiping it.

    Args:
        credential: The client's authentication response (JSON string or dict).
        stored: The persisted credential the client claims (looked up by id);
            must expose ``public_key`` and ``sign_count``.
        config: The relying-party config.
        require_user_verification: Override the UV requirement; defaults to
            ``config.require_user_verification``.

    Raises:
        PasskeyChallengeError: No valid challenge (missing/expired/replayed).
        PasskeyVerificationError: The assertion failed any check.

    Returns:
        An :class:`AuthenticatedCredential` with the new sign count and the
        clone-detection regression signal.
    """
    webauthn = _require_webauthn()
    from webauthn.helpers.exceptions import WebAuthnException

    challenge = _consume_challenge()
    ruv = (
        config.require_user_verification
        if require_user_verification is None
        else require_user_verification
    )
    try:
        verified = webauthn.verify_authentication_response(
            credential=credential,
            expected_challenge=challenge,
            expected_rp_id=config.rp_id,
            expected_origin=config.expected_origin,
            credential_public_key=stored.public_key,
            credential_current_sign_count=stored.sign_count,
            require_user_verification=ruv,
        )
    except WebAuthnException:
        raise PasskeyVerificationError("Passkey authentication could not be verified.") from None

    regressed = verified.new_sign_count != 0 and verified.new_sign_count <= stored.sign_count
    return AuthenticatedCredential(
        credential_id=verified.credential_id,
        new_sign_count=verified.new_sign_count,
        user_verified=bool(verified.user_verified),
        credential_device_type=str(verified.credential_device_type),
        credential_backed_up=bool(verified.credential_backed_up),
        sign_count_regressed=regressed,
    )
