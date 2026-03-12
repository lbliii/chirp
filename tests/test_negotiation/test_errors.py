"""Tests for negotiation error handling."""

import pytest

from chirp.server.negotiation import negotiate


class TestNegotiateErrors:
    def test_unknown_type_raises(self) -> None:
        with pytest.raises(TypeError, match="Cannot convert"):
            negotiate(42)

    def test_error_message_helpful(self) -> None:
        with pytest.raises(TypeError, match="int"):
            negotiate(42)
