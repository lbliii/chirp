"""Tests for Action and FormAction negotiation."""

import json

from kida import Environment

from chirp.http.request import Request
from chirp.server.negotiation import negotiate
from chirp.templating.returns import Action, FormAction, Fragment


class TestNegotiateAction:
    def test_action_defaults_to_204_no_content(self) -> None:
        result = negotiate(Action())
        assert result.status == 204
        assert result.text == ""
        assert "text/html" in result.content_type

    def test_action_sets_hx_headers(self) -> None:
        result = negotiate(Action(trigger="saved", refresh=True))
        assert result.status == 204
        assert ("HX-Trigger", "saved") in result.headers
        assert ("HX-Refresh", "true") in result.headers

    def test_action_trigger_payload_dict(self) -> None:
        result = negotiate(Action(trigger={"saved": {"ok": True}}))
        assert result.status == 204
        assert ("HX-Trigger", json.dumps({"saved": {"ok": True}})) in result.headers


class TestNegotiateFormAction:
    """Tests for FormAction negotiation — progressive enhancement for form success."""

    @staticmethod
    def _plain_request() -> Request:
        """Create a plain (non-htmx) request."""

        async def _receive():
            return {"type": "http.request", "body": b"", "more_body": False}

        return Request.from_asgi(
            {
                "type": "http",
                "method": "POST",
                "path": "/submit",
                "headers": [],
                "query_string": b"",
                "http_version": "1.1",
                "server": ("127.0.0.1", 8000),
                "client": ("127.0.0.1", 1234),
            },
            receive=_receive,
        )

    @staticmethod
    def _htmx_request() -> Request:
        """Create a fake htmx request (is_fragment=True)."""

        async def _receive():
            return {"type": "http.request", "body": b"", "more_body": False}

        return Request.from_asgi(
            {
                "type": "http",
                "method": "POST",
                "path": "/submit",
                "headers": [(b"hx-request", b"true")],
                "query_string": b"",
                "http_version": "1.1",
                "server": ("127.0.0.1", 8000),
                "client": ("127.0.0.1", 1234),
            },
            receive=_receive,
        )

    def test_non_htmx_redirects(self) -> None:
        request = self._plain_request()
        result = negotiate(FormAction("/thanks"), request=request)
        assert result.status == 303
        assert ("Location", "/thanks") in result.headers

    def test_non_htmx_custom_status(self) -> None:
        request = self._plain_request()
        result = negotiate(FormAction("/moved", status=301), request=request)
        assert result.status == 301
        assert ("Location", "/moved") in result.headers

    def test_non_htmx_ignores_fragments(self, kida_env: Environment) -> None:
        request = self._plain_request()
        result = negotiate(
            FormAction(
                "/contacts",
                Fragment("search.html", "results_list", results=["a"]),
            ),
            kida_env=kida_env,
            request=request,
        )
        assert result.status == 303
        assert ("Location", "/contacts") in result.headers

    def test_htmx_no_fragments_sends_hx_redirect(self) -> None:
        request = self._htmx_request()
        result = negotiate(FormAction("/dashboard"), request=request)
        assert result.status == 200
        assert ("HX-Redirect", "/dashboard") in result.headers

    def test_htmx_with_fragments_renders_html(self, kida_env: Environment) -> None:
        request = self._htmx_request()
        result = negotiate(
            FormAction(
                "/contacts",
                Fragment("search.html", "results_list", results=["alpha", "beta"]),
            ),
            kida_env=kida_env,
            request=request,
        )
        assert result.status == 200
        assert "alpha" in result.text
        assert "beta" in result.text
        header_names = {name for name, _ in result.headers}
        assert "HX-Redirect" not in header_names

    def test_htmx_with_trigger(self, kida_env: Environment) -> None:
        request = self._htmx_request()
        result = negotiate(
            FormAction(
                "/contacts",
                Fragment("search.html", "results_list", results=[]),
                trigger="contactAdded",
            ),
            kida_env=kida_env,
            request=request,
        )
        assert ("HX-Trigger", "contactAdded") in result.headers

    def test_htmx_without_trigger(self, kida_env: Environment) -> None:
        request = self._htmx_request()
        result = negotiate(
            FormAction(
                "/contacts",
                Fragment("search.html", "results_list", results=[]),
            ),
            kida_env=kida_env,
            request=request,
        )
        header_names = {name for name, _ in result.headers}
        assert "HX-Trigger" not in header_names

    def test_htmx_multiple_fragments(self, kida_env: Environment) -> None:
        request = self._htmx_request()
        result = negotiate(
            FormAction(
                "/ok",
                Fragment("search.html", "results_list", results=["x"]),
                Fragment("cart.html", "counter", count=42),
            ),
            kida_env=kida_env,
            request=request,
        )
        assert "x" in result.text
        assert "42" in result.text
        assert result.render_intent == "fragment"

    def test_htmx_secondary_fragments_get_oob_wrapping(self, kida_env: Environment) -> None:
        """Secondary fragments in MutationResult must have hx-swap-oob for htmx to swap them."""
        request = self._htmx_request()
        result = negotiate(
            FormAction(
                "/ok",
                Fragment("search.html", "results_list", results=["primary"]),
                Fragment("cart.html", "counter", target="cart-count", count=7),
            ),
            kida_env=kida_env,
            request=request,
        )
        # Primary fragment rendered without OOB wrapper
        assert "primary" in result.text
        # Secondary fragment wrapped with OOB swap targeting its declared target
        assert 'id="cart-count"' in result.text
        assert 'hx-swap-oob=' in result.text
