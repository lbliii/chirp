"""Tests for chirp.http.cookies — parse_cookies + SetCookie."""

import pytest

from chirp.http.cookies import SetCookie, parse_cookies


class TestParseCookies:
    def test_empty_string(self) -> None:
        assert parse_cookies("") == {}

    def test_single_cookie(self) -> None:
        assert parse_cookies("session=abc123") == {"session": "abc123"}

    def test_multiple_cookies(self) -> None:
        result = parse_cookies("session=abc; theme=dark; lang=en")
        assert result == {"session": "abc", "theme": "dark", "lang": "en"}

    def test_whitespace_handling(self) -> None:
        result = parse_cookies("  session = abc ;  theme = dark  ")
        assert result == {"session": "abc", "theme": "dark"}

    def test_value_with_equals(self) -> None:
        """Values can contain '=' (e.g. base64)."""
        result = parse_cookies("token=abc=def=")
        assert result == {"token": "abc=def="}

    def test_empty_value(self) -> None:
        result = parse_cookies("flag=")
        assert result == {"flag": ""}

    def test_no_equals_ignored(self) -> None:
        """Pairs without '=' are silently skipped."""
        result = parse_cookies("session=abc; broken; theme=dark")
        assert result == {"session": "abc", "theme": "dark"}

    def test_duplicate_keys_last_wins(self) -> None:
        result = parse_cookies("a=1; a=2")
        assert result == {"a": "2"}


class TestSetCookie:
    def test_minimal(self) -> None:
        c = SetCookie(name="session", value="abc")
        header = c.to_header_value()

        assert header.startswith("session=abc")
        assert "Path=/" in header
        assert "HttpOnly" in header
        assert "SameSite=lax" in header

    def test_all_attributes(self) -> None:
        c = SetCookie(
            name="session",
            value="abc",
            max_age=3600,
            path="/app",
            domain=".example.com",
            secure=True,
            httponly=True,
            samesite="strict",
        )
        header = c.to_header_value()

        assert "Max-Age=3600" in header
        assert "Path=/app" in header
        assert "Domain=.example.com" in header
        assert "Secure" in header
        assert "HttpOnly" in header
        assert "SameSite=strict" in header

    def test_delete_cookie(self) -> None:
        """Max-Age=0 signals cookie deletion."""
        c = SetCookie(name="session", value="", max_age=0)
        header = c.to_header_value()

        assert "Max-Age=0" in header

    def test_frozen(self) -> None:
        c = SetCookie(name="a", value="b")

        with pytest.raises(AttributeError):
            c.name = "c"  # type: ignore[misc]

    def test_no_max_age_omitted(self) -> None:
        c = SetCookie(name="a", value="b")
        assert "Max-Age" not in c.to_header_value()

    def test_no_domain_omitted(self) -> None:
        c = SetCookie(name="a", value="b")
        assert "Domain" not in c.to_header_value()
