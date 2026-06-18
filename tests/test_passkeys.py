"""Tests for chirp.security.passkeys — ceremony codec + challenge lifecycle.

The WebAuthn crypto itself is py_webauthn's job and is not re-tested here. These
tests pin the *wrapper* contract: challenge stash/pop (single-use, embedded TTL,
pop-before-verify), the options-JSON shape the JS bridge consumes, fail-closed
exception wrapping (WebAuthnException → generic PasskeyVerificationError), and
the lazy-import guarantee that ``import chirp`` never pulls in ``webauthn``.

Ceremony tests need the optional ``webauthn`` dep (``pip install chirp[passkeys]``
/ ``uv run --with 'webauthn>=2.8,<3'``); they skip when it is absent, mirroring
the argon2 handling in test_passwords.py.
"""

import subprocess
import sys
import time

import pytest

from chirp.errors import ConfigurationError
from chirp.security.passkeys import (
    CHALLENGE_SESSION_KEY,
    AuthenticatedCredential,
    PasskeyChallengeError,
    PasskeyConfig,
    PasskeyCredential,
    PasskeyVerificationError,
    RegisteredCredential,
    _b64u_decode,
    _b64u_encode,
    _extract_transports,
    _has_webauthn,
    _pop_challenge,
    _require_webauthn,
    _stash_challenge,
    begin_authentication,
    begin_registration,
    finish_authentication,
    finish_registration,
)

PK = PasskeyConfig(rp_id="example.com", rp_name="Example", origin="https://example.com")

requires_webauthn = pytest.mark.skipif(
    not _has_webauthn(), reason="webauthn not installed (pip install chirp[passkeys])"
)


@pytest.fixture
def session():
    """Activate an empty request-scoped session dict and yield it."""
    from chirp.middleware.sessions import _session_var

    token = _session_var.set({})
    try:
        yield _session_var.get()
    finally:
        _session_var.reset(token)


# ---------------------------------------------------------------------------
# PasskeyConfig — fail-loud construction
# ---------------------------------------------------------------------------


class TestPasskeyConfig:
    def test_defaults(self) -> None:
        assert PK.user_verification == "preferred"
        assert PK.resident_key == "preferred"  # serves username-first + usernameless
        assert PK.attestation == "none"
        assert PK.timeout == 60000
        assert PK.challenge_ttl_seconds == 300
        assert PK.require_user_verification is False

    def test_expected_origin_str_passthrough(self) -> None:
        assert PK.expected_origin == "https://example.com"

    def test_expected_origin_tuple_becomes_list(self) -> None:
        cfg = PasskeyConfig(
            rp_id="example.com",
            rp_name="Example",
            origin=("https://a.example.com", "https://b.example.com"),
        )
        assert cfg.expected_origin == ["https://a.example.com", "https://b.example.com"]

    def test_require_user_verification_when_required(self) -> None:
        cfg = PasskeyConfig(
            rp_id="example.com",
            rp_name="Example",
            origin="https://example.com",
            user_verification="required",
        )
        assert cfg.require_user_verification is True

    @pytest.mark.parametrize(
        "kwargs",
        [
            {"rp_id": ""},
            {"rp_name": ""},
            {"origin": ""},
            {"user_verification": "maybe"},
            {"resident_key": "sometimes"},
            {"attestation": "bogus"},
            {"challenge_ttl_seconds": 0},
            {"challenge_ttl_seconds": -5},
        ],
    )
    def test_invalid_config_fails_loud(self, kwargs) -> None:
        base = {"rp_id": "example.com", "rp_name": "Example", "origin": "https://example.com"}
        base.update(kwargs)
        with pytest.raises(ConfigurationError):
            PasskeyConfig(**base)

    def test_is_frozen(self) -> None:
        with pytest.raises((AttributeError, TypeError)):
            PK.rp_id = "evil.com"  # type: ignore[misc]

    @pytest.mark.parametrize(
        ("rp_id", "origin"),
        [
            ("example.com", "https://example.com"),  # host == rp_id
            ("example.com", "https://app.example.com"),  # subdomain
            ("example.com", "https://deep.app.example.com"),  # deeper subdomain
            ("localhost", "http://localhost:8000"),  # dev
            ("example.com", ("https://example.com", "https://app.example.com")),  # multi-origin
        ],
    )
    def test_valid_rp_id_origin_pairs(self, rp_id, origin) -> None:
        PasskeyConfig(rp_id=rp_id, rp_name="X", origin=origin)  # no raise

    @pytest.mark.parametrize(
        ("rp_id", "origin"),
        [
            ("example.com", "https://evil.com"),  # unrelated host
            ("example.com", "https://notexample.com"),  # suffix-string but not a domain boundary
            ("app.example.com", "https://example.com"),  # rp_id is a CHILD, not a parent
            ("example.com", "example.com"),  # missing scheme → no host
            ("example.com", ("https://example.com", "https://evil.com")),  # one bad origin
        ],
    )
    def test_invalid_rp_id_origin_pairs_fail_loud(self, rp_id, origin) -> None:
        with pytest.raises(ConfigurationError):
            PasskeyConfig(rp_id=rp_id, rp_name="X", origin=origin)


# ---------------------------------------------------------------------------
# base64url codec + transport extraction
# ---------------------------------------------------------------------------


class TestCodec:
    @pytest.mark.parametrize("raw", [b"", b"\x00", b"abc", b"\xff" * 64, bytes(range(256))])
    def test_b64u_roundtrip(self, raw) -> None:
        assert _b64u_decode(_b64u_encode(raw)) == raw

    def test_b64u_is_unpadded_urlsafe(self) -> None:
        encoded = _b64u_encode(b"\xfb\xff\xfe")
        assert "=" not in encoded
        assert "+" not in encoded
        assert "/" not in encoded

    def test_extract_transports_from_dict(self) -> None:
        cred = {"response": {"transports": ["internal", "hybrid"]}}
        assert _extract_transports(cred) == ("internal", "hybrid")

    def test_extract_transports_from_json_string(self) -> None:
        assert _extract_transports('{"response": {"transports": ["usb"]}}') == ("usb",)

    @pytest.mark.parametrize(
        "cred",
        ["not json", "{}", '{"response": {}}', '{"response": {"transports": "usb"}}', "[]"],
    )
    def test_extract_transports_absent_or_bad(self, cred) -> None:
        assert _extract_transports(cred) is None


# ---------------------------------------------------------------------------
# Challenge lifecycle — single-use, embedded TTL, fail-loud without a session
# ---------------------------------------------------------------------------


class TestChallengeLifecycle:
    def test_stash_then_pop_roundtrips(self, session) -> None:
        _stash_challenge(b"a-random-challenge", ttl=300)
        assert session[CHALLENGE_SESSION_KEY]["c"]  # stored b64url
        assert _pop_challenge() == b"a-random-challenge"

    def test_pop_is_single_use(self, session) -> None:
        _stash_challenge(b"once", ttl=300)
        assert _pop_challenge() == b"once"
        assert _pop_challenge() is None  # consumed
        assert CHALLENGE_SESSION_KEY not in session

    def test_expired_challenge_pops_none_and_is_removed(self, session) -> None:
        _stash_challenge(b"stale", ttl=300)
        session[CHALLENGE_SESSION_KEY]["exp"] = time.time() - 1  # force expiry
        assert _pop_challenge() is None
        assert CHALLENGE_SESSION_KEY not in session  # removed even when expired (anti-replay)

    def test_missing_challenge_pops_none(self, session) -> None:
        assert _pop_challenge() is None

    @pytest.mark.parametrize(
        "entry",
        ["not-a-dict", {"c": "abc"}, {"exp": 99999999999}, {"c": 123, "exp": 99999999999}],
    )
    def test_malformed_entry_pops_none(self, session, entry) -> None:
        session[CHALLENGE_SESSION_KEY] = entry
        assert _pop_challenge() is None

    def test_stash_without_session_raises_lookup(self) -> None:
        # No `session` fixture → no active SessionMiddleware → fail loud.
        with pytest.raises(LookupError):
            _stash_challenge(b"x", ttl=300)


# ---------------------------------------------------------------------------
# Dependency guard
# ---------------------------------------------------------------------------


class TestDependencyGuard:
    def test_require_webauthn_raises_configuration_error_when_absent(self, monkeypatch) -> None:
        # Setting sys.modules['webauthn'] = None makes `import webauthn` raise ImportError.
        monkeypatch.setitem(sys.modules, "webauthn", None)
        with pytest.raises(ConfigurationError, match="chirp\\[passkeys\\]"):
            _require_webauthn()

    @requires_webauthn
    def test_require_webauthn_returns_module_when_present(self) -> None:
        mod = _require_webauthn()
        assert hasattr(mod, "generate_registration_options")


# ---------------------------------------------------------------------------
# Ceremony codec (needs webauthn)
# ---------------------------------------------------------------------------


@requires_webauthn
class TestRegistrationCeremony:
    def test_begin_returns_options_json_and_stashes_challenge(self, session) -> None:
        options = begin_registration(user_id=b"user-123", user_name="alice@example.com", config=PK)
        # Wire shape the JS bridge expects (camelCase, base64url'd bytes).
        assert options["rp"]["id"] == "example.com"
        assert options["rp"]["name"] == "Example"
        assert options["user"]["name"] == "alice@example.com"
        assert isinstance(options["challenge"], str)
        assert "pubKeyCredParams" in options
        assert options["authenticatorSelection"]["residentKey"] == "preferred"
        assert options["authenticatorSelection"]["userVerification"] == "preferred"
        # The exact challenge bytes are stashed (b64url) for the matching finish.
        assert _pop_challenge() == _b64u_decode(options["challenge"])

    def test_exclude_credentials_serialized(self, session) -> None:
        options = begin_registration(
            user_id=b"u", user_name="a", exclude_credentials=[b"existing-cred-id"], config=PK
        )
        assert options["excludeCredentials"]
        assert options["excludeCredentials"][0]["id"] == _b64u_encode(b"existing-cred-id")

    def test_finish_pops_challenge_before_verify_and_wraps_failure(self, session) -> None:
        # A valid challenge is present, but the credential is bogus: verify must
        # raise WebAuthnException, which the verb wraps as PasskeyVerificationError
        # (no leak of the specific check), AND the challenge must be consumed.
        begin_registration(user_id=b"u", user_name="a", config=PK)
        assert CHALLENGE_SESSION_KEY in session
        with pytest.raises(PasskeyVerificationError):
            finish_registration(credential='{"bogus": true}', config=PK)
        assert CHALLENGE_SESSION_KEY not in session  # popped before verify (anti-replay)

    def test_finish_without_challenge_raises_challenge_error(self, session) -> None:
        with pytest.raises(PasskeyChallengeError):
            finish_registration(credential='{"bogus": true}', config=PK)


@requires_webauthn
class TestAuthenticationCeremony:
    def test_begin_returns_options_json_and_stashes_challenge(self, session) -> None:
        options = begin_authentication(config=PK)
        assert options["rpId"] == "example.com"
        assert isinstance(options["challenge"], str)
        assert options["userVerification"] == "preferred"
        assert _pop_challenge() == _b64u_decode(options["challenge"])

    def test_allow_credentials_serialized(self, session) -> None:
        options = begin_authentication(allow_credentials=[b"cred-1"], config=PK)
        assert options["allowCredentials"][0]["id"] == _b64u_encode(b"cred-1")

    def test_empty_allow_credentials_omitted_for_usernameless(self, session) -> None:
        options = begin_authentication(allow_credentials=[], config=PK)
        # [] must not be sent as "no credential allowed"; discoverable login wants it absent/empty.
        assert not options.get("allowCredentials")

    def test_finish_pops_challenge_before_verify_and_wraps_failure(self, session) -> None:
        begin_authentication(config=PK)
        stored = _FakeStored(credential_id=b"cred-1", public_key=b"\x00" * 32, sign_count=0)
        with pytest.raises(PasskeyVerificationError):
            finish_authentication(credential='{"bogus": true}', stored=stored, config=PK)
        assert CHALLENGE_SESSION_KEY not in session

    def test_finish_without_challenge_raises_challenge_error(self, session) -> None:
        stored = _FakeStored(credential_id=b"cred-1", public_key=b"\x00" * 32, sign_count=0)
        with pytest.raises(PasskeyChallengeError):
            finish_authentication(credential='{"bogus": true}', stored=stored, config=PK)


class _FakeStored:
    """Minimal object satisfying the PasskeyCredential protocol."""

    def __init__(self, *, credential_id: bytes, public_key: bytes, sign_count: int) -> None:
        self.credential_id = credential_id
        self.public_key = public_key
        self.sign_count = sign_count
        self.user_id = "user-1"


class TestProtocolAndDTOs:
    def test_fake_store_satisfies_protocol(self) -> None:
        stored = _FakeStored(credential_id=b"c", public_key=b"k", sign_count=3)
        assert isinstance(stored, PasskeyCredential)

    def test_registered_credential_is_frozen(self) -> None:
        cred = RegisteredCredential(
            credential_id=b"c",
            public_key=b"k",
            sign_count=0,
            aaguid="0" * 36,
            fmt="none",
            credential_device_type="multi_device",
            credential_backed_up=True,
            user_verified=True,
        )
        with pytest.raises((AttributeError, TypeError)):
            cred.sign_count = 9  # type: ignore[misc]

    def test_authenticated_credential_carries_regression_signal(self) -> None:
        ac = AuthenticatedCredential(
            credential_id=b"c",
            new_sign_count=5,
            user_verified=True,
            credential_device_type="single_device",
            credential_backed_up=False,
            sign_count_regressed=True,
        )
        assert ac.sign_count_regressed is True


# ---------------------------------------------------------------------------
# Lazy-import guarantee — `import chirp` must never import webauthn (or argon2,
# itsdangerous, …). This guard did not previously exist anywhere in the suite.
# ---------------------------------------------------------------------------


class TestLazyImport:
    def _modules_after(self, import_stmt: str) -> set[str]:
        code = f"import sys; {import_stmt}; print('\\n'.join(sorted(sys.modules)))"
        out = subprocess.run(
            [sys.executable, "-c", code], capture_output=True, text=True, check=True
        )
        return set(out.stdout.split())

    def test_import_chirp_does_not_import_webauthn(self) -> None:
        assert "webauthn" not in self._modules_after("import chirp")

    def test_import_passkeys_module_does_not_import_webauthn(self) -> None:
        # Importing the module itself must stay light — webauthn is pulled in
        # only when a verb actually runs.
        mods = self._modules_after("import chirp.security.passkeys")
        assert "webauthn" not in mods
        # And it must not drag in itsdangerous via the session layer either.
        assert "itsdangerous" not in mods
