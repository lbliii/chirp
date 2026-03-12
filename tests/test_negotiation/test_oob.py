"""Tests for OOB multi-fragment out-of-band swap responses."""

import pytest
from kida import Environment

from chirp.server.negotiation import negotiate
from chirp.templating.returns import OOB, Fragment, Template


class TestNegotiateOOB:
    """Tests for OOB multi-fragment out-of-band swap responses."""

    def test_single_oob_fragment(self, kida_env: Environment) -> None:
        result = negotiate(
            OOB(
                Fragment("search.html", "results_list", results=["main"]),
                Fragment("cart.html", "counter", count=5),
            ),
            kida_env=kida_env,
        )
        assert result.status == 200
        assert "text/html" in result.content_type
        # Main fragment rendered first
        assert "main" in result.text
        # OOB fragment wrapped with hx-swap-oob
        assert 'hx-swap-oob="true"' in result.text
        assert 'id="counter"' in result.text
        assert "5" in result.text

    def test_multiple_oob_fragments(self, kida_env: Environment) -> None:
        result = negotiate(
            OOB(
                Fragment("search.html", "results_list", results=["primary"]),
                Fragment("cart.html", "counter", count=3),
                Fragment("cart.html", "summary", total=7),
            ),
            kida_env=kida_env,
        )
        text = result.text
        # Both OOB fragments present
        assert 'id="counter"' in text
        assert 'id="summary"' in text
        assert text.count('hx-swap-oob="true"') == 2

    def test_oob_uses_block_name_as_default_target(self, kida_env: Environment) -> None:
        result = negotiate(
            OOB(
                Fragment("search.html", "results_list", results=[]),
                Fragment("cart.html", "counter", count=0),
            ),
            kida_env=kida_env,
        )
        # block_name "counter" used as target ID
        assert 'id="counter"' in result.text

    def test_oob_explicit_target_overrides_block_name(self, kida_env: Environment) -> None:
        result = negotiate(
            OOB(
                Fragment("search.html", "results_list", results=[]),
                Fragment("cart.html", "counter", target="cart-counter", count=0),
            ),
            kida_env=kida_env,
        )
        # Explicit target used instead of block name
        assert 'id="cart-counter"' in result.text
        assert 'id="counter"' not in result.text

    def test_main_as_template(self, kida_env: Environment) -> None:
        result = negotiate(
            OOB(
                Template("page.html", title="Full"),
                Fragment("cart.html", "counter", count=1),
            ),
            kida_env=kida_env,
        )
        # Full template rendered as main
        assert "<title>Full</title>" in result.text
        # OOB fragment appended
        assert 'hx-swap-oob="true"' in result.text

    def test_without_env_raises(self) -> None:
        from chirp.errors import ConfigurationError

        with pytest.raises(ConfigurationError, match="requires kida integration"):
            negotiate(
                OOB(
                    Fragment("search.html", "results_list", results=[]),
                    Fragment("cart.html", "counter", count=0),
                )
            )
