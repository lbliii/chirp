"""Tests for ValidationError negotiation."""

import pytest
from kida import Environment

from chirp.server.negotiation import negotiate
from chirp.templating.returns import ValidationError


class TestNegotiateValidationError:
    """Tests for ValidationError negotiation — 422 + fragment + optional HX-Retarget."""

    def test_renders_fragment_with_422(self, kida_env: Environment) -> None:
        result = negotiate(
            ValidationError(
                "form.html",
                "form_body",
                errors={"email": ["Required"]},
                form={"email": ""},
            ),
            kida_env=kida_env,
        )
        assert result.status == 422
        assert "text/html" in result.content_type
        assert "email: Required" in result.text
        # Should be a fragment, not the full page
        assert "<html>" not in result.text

    def test_without_retarget_has_no_hx_header(self, kida_env: Environment) -> None:
        result = negotiate(
            ValidationError("form.html", "form_body", errors={}),
            kida_env=kida_env,
        )
        assert result.status == 422
        header_names = {name for name, _ in result.headers}
        assert "HX-Retarget" not in header_names
        assert "HX-Reselect" not in header_names

    def test_with_retarget_sets_header(self, kida_env: Environment) -> None:
        result = negotiate(
            ValidationError(
                "form.html",
                "form_errors",
                retarget="#error-banner",
                errors={"email": ["Invalid"]},
            ),
            kida_env=kida_env,
        )
        assert result.status == 422
        assert ("HX-Retarget", "#error-banner") in result.headers
        assert "email: Invalid" in result.text

    def test_without_env_raises(self) -> None:
        from chirp.errors import ConfigurationError

        with pytest.raises(ConfigurationError, match="requires kida integration"):
            negotiate(ValidationError("form.html", "form_body", errors={}))
