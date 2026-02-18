"""Tests for is_safe_url — open redirect prevention."""

from chirp.security.urls import is_safe_url


class TestIsSafeUrl:
    """Unit tests for is_safe_url()."""

    # -- Safe URLs --

    def test_simple_path(self) -> None:
        assert is_safe_url("/dashboard") is True

    def test_root(self) -> None:
        assert is_safe_url("/") is True

    def test_path_with_query(self) -> None:
        assert is_safe_url("/login?next=/home") is True

    def test_nested_path(self) -> None:
        assert is_safe_url("/a/b/c") is True

    def test_path_with_fragment(self) -> None:
        assert is_safe_url("/page#section") is True

    def test_path_with_encoded_chars(self) -> None:
        assert is_safe_url("/path%20with%20spaces") is True

    # -- Unsafe URLs --

    def test_empty_string(self) -> None:
        assert is_safe_url("") is False

    def test_protocol_relative(self) -> None:
        assert is_safe_url("//evil.com") is False

    def test_protocol_relative_with_path(self) -> None:
        assert is_safe_url("//evil.com/steal") is False

    def test_https_absolute(self) -> None:
        assert is_safe_url("https://evil.com") is False

    def test_http_absolute(self) -> None:
        assert is_safe_url("http://evil.com") is False

    def test_javascript_scheme(self) -> None:
        assert is_safe_url("javascript://alert(1)") is False

    def test_relative_without_slash(self) -> None:
        assert is_safe_url("dashboard") is False

    def test_none_value(self) -> None:
        # Type-wise this shouldn't happen, but defensive check
        assert is_safe_url(None) is False  # type: ignore[arg-type]

    def test_ftp_scheme(self) -> None:
        assert is_safe_url("ftp://files.example.com") is False

    def test_data_scheme(self) -> None:
        assert is_safe_url("data://text/html,<h1>hi</h1>") is False
