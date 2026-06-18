"""Tests for the passkeys JS bridge — snippet shape, nonce, dedup, injection.

Mirrors test_islands.py / test_alpine.py. The bridge is self-contained (no
external ``src``), so the CDN-footgun class that test_alpine.py guards against
cannot exist here — and that absence is asserted explicitly. Browser behavior
(navigator.credentials) is not exercised by TestClient and must be verified in a
real browser.
"""

from chirp import App
from chirp.config import AppConfig
from chirp.server.passkeys import passkeys_snippet
from chirp.testing import TestClient


class TestPasskeysSnippet:
    def test_has_dedup_marker_and_namespace(self) -> None:
        s = passkeys_snippet("1")
        assert 'data-chirp="passkeys"' in s
        assert "window.chirp.passkeys" in s
        assert "window.chirp = window.chirp || {}" in s

    def test_exposes_register_and_authenticate(self) -> None:
        s = passkeys_snippet("1")
        assert "register: register" in s
        assert "authenticate: authenticate" in s
        assert "isSupported" in s
        assert "isConditionalSupported" in s

    def test_idempotent_injection_guard(self) -> None:
        assert "if (window.chirp && window.chirp.passkeys) return;" in passkeys_snippet("1")

    def test_codec_and_native_paths_present(self) -> None:
        s = passkeys_snippet("1")
        # base64url codec (the marshalling glue worth vendoring)
        assert "b64uToBuf" in s
        assert "bufToB64u" in s
        # native fast-path + manual fallback
        assert "parseCreationOptionsFromJSON" in s
        assert "parseRequestOptionsFromJSON" in s
        assert "cred.toJSON" in s

    def test_domexception_mapping(self) -> None:
        s = passkeys_snippet("1")
        assert "NotAllowedError" in s
        assert "cancelled" in s
        assert "InvalidStateError" in s
        assert "duplicate" in s
        # SecurityError → misconfigured + loud developer console error
        assert "SecurityError" in s
        assert "misconfigured" in s
        assert "console.error" in s
        assert "passkeyReason" in s

    def test_version_embedded(self) -> None:
        assert 'VERSION = "7"' in passkeys_snippet("7")

    def test_no_external_src_no_cdn_footgun(self) -> None:
        """The bridge loads nothing external — no CDN URL, no <script src>."""
        s = passkeys_snippet("1")
        assert "src=" not in s
        assert "http://" not in s
        assert "https://" not in s
        assert "cdn." not in s
        assert "jsdelivr" not in s

    def test_default_is_unnonced(self) -> None:
        assert "nonce=" not in passkeys_snippet("1")

    def test_nonce_kwarg_adds_attr(self) -> None:
        s = passkeys_snippet("1", nonce="PKNONCE")
        assert '<script data-chirp="passkeys" nonce="PKNONCE">' in s


class TestPasskeysInjection:
    async def test_injected_when_enabled(self) -> None:
        app = App(config=AppConfig(passkeys=True))

        @app.route("/")
        def index():
            return "<html><body><h1>Login</h1></body></html>"

        async with TestClient(app) as client:
            response = await client.get("/")
            assert response.status == 200
            assert 'data-chirp="passkeys"' in response.text
            assert "window.chirp.passkeys" in response.text

    async def test_not_injected_on_fragment_request(self) -> None:
        app = App(config=AppConfig(passkeys=True))

        @app.route("/")
        def index():
            return "<div>fragment</div>"

        async with TestClient(app) as client:
            response = await client.get("/", headers={"HX-Request": "true"})
            assert response.status == 200
            assert 'data-chirp="passkeys"' not in response.text

    async def test_not_injected_on_json_response(self) -> None:
        app = App(config=AppConfig(passkeys=True))

        @app.route("/api")
        def api():
            return {"ok": True}

        async with TestClient(app) as client:
            response = await client.get("/api")
            assert response.status == 200
            assert 'data-chirp="passkeys"' not in response.text

    async def test_not_injected_when_disabled(self) -> None:
        app = App(config=AppConfig())  # passkeys defaults False

        @app.route("/")
        def index():
            return "<html><body>Hi</body></html>"

        async with TestClient(app) as client:
            response = await client.get("/")
            assert 'data-chirp="passkeys"' not in response.text

    async def test_nonce_flows_under_csp(self) -> None:
        app = App(config=AppConfig(passkeys=True, csp_nonce_enabled=True))

        @app.route("/")
        def index():
            return "<html><body>Hi</body></html>"

        async with TestClient(app) as client:
            response = await client.get("/")
            assert 'data-chirp="passkeys"' in response.text
            # Under a nonce mechanism the injected bridge must carry a nonce.
            assert 'data-chirp="passkeys" nonce="' in response.text
