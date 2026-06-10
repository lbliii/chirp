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

    def test_tenant_prefixed_path(self) -> None:
        assert is_safe_url("/c/acme/boards/ic?tab=cast") is True

    def test_tenant_prefixed_next_value(self) -> None:
        assert is_safe_url("/login?next=/c/acme/boards/ic") is True

    def test_nested_path(self) -> None:
        assert is_safe_url("/a/b/c") is True

    def test_nested_path_with_query(self) -> None:
        assert is_safe_url("/a/b?x=1") is True

    def test_relative_next_value_in_query(self) -> None:
        # A relative target carried in the query is still same-origin.
        assert is_safe_url("/a?next=/b") is True

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

    def test_encoded_absolute_url_without_leading_slash(self) -> None:
        assert is_safe_url("https%3A%2F%2Fevil.com") is False

    def test_absolute_url_hidden_in_query_is_rejected(self) -> None:
        assert is_safe_url("/login?next=https://evil.com") is False

    # -- Backslash open-redirect (browsers normalize "\" -> "/") --

    def test_backslash_protocol_relative_double(self) -> None:
        # "\\evil.com" -> browser normalizes to "//evil.com": protocol-relative.
        assert is_safe_url("\\\\evil.com") is False

    def test_backslash_single_leading(self) -> None:
        # A bare leading "\" is never a legitimate relative path; reject it.
        assert is_safe_url("\\evil.com") is False

    def test_slash_then_backslash(self) -> None:
        # "/\evil.com" -> browser normalizes to "//evil.com": protocol-relative.
        assert is_safe_url("/\\evil.com") is False

    def test_slash_then_double_backslash(self) -> None:
        assert is_safe_url("/\\\\evil.com") is False

    def test_backslash_with_path(self) -> None:
        assert is_safe_url("\\\\evil.com/steal") is False

    def test_mixed_slash_backslash_authority(self) -> None:
        # "\/evil.com" -> "//evil.com" after normalization.
        assert is_safe_url("\\/evil.com") is False

    # -- Leading control / whitespace bytes (browsers strip them) --

    def test_leading_nul_then_protocol_relative(self) -> None:
        assert is_safe_url("\x00//evil.com") is False

    def test_leading_tab_then_protocol_relative(self) -> None:
        assert is_safe_url("\t//evil.com") is False

    def test_leading_newline_then_protocol_relative(self) -> None:
        assert is_safe_url("\n//evil.com") is False

    def test_leading_cr_then_protocol_relative(self) -> None:
        assert is_safe_url("\r//evil.com") is False

    def test_leading_space_then_protocol_relative(self) -> None:
        assert is_safe_url(" //evil.com") is False

    def test_leading_control_then_scheme(self) -> None:
        assert is_safe_url("\x01\x02https://evil.com") is False

    def test_leading_control_then_backslash(self) -> None:
        assert is_safe_url("\x00\\\\evil.com") is False

    def test_only_control_chars(self) -> None:
        # Strips to empty: nothing safe remains.
        assert is_safe_url("\x00\t\n ") is False

    def test_leading_control_preserves_legit_path(self) -> None:
        # Stripping leading control bytes must not promote-then-reject a real
        # relative path that happens to be preceded by whitespace.
        assert is_safe_url("\t/dashboard") is True
