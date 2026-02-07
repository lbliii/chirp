"""Tests for chirp.testing — fragment assertion helpers."""

import pytest

from chirp.http.response import Response
from chirp.testing import (
    assert_fragment_contains,
    assert_fragment_not_contains,
    assert_is_error_fragment,
    assert_is_fragment,
)


class TestAssertIsFragment:
    """assert_is_fragment succeeds for fragments, fails for full pages."""

    def test_passes_for_fragment(self) -> None:
        response = Response(body='<div id="results">items</div>', status=200)
        assert_is_fragment(response)

    def test_fails_for_full_page(self) -> None:
        response = Response(body="<html><body>page</body></html>", status=200)
        with pytest.raises(AssertionError, match="full page"):
            assert_is_fragment(response)

    def test_fails_for_wrong_status(self) -> None:
        response = Response(body="<div>ok</div>", status=404)
        with pytest.raises(AssertionError, match="Expected status 200"):
            assert_is_fragment(response)

    def test_custom_status(self) -> None:
        response = Response(body="<div>created</div>", status=201)
        assert_is_fragment(response, status=201)

    def test_fails_for_empty_body(self) -> None:
        response = Response(body="", status=200)
        with pytest.raises(AssertionError, match="empty"):
            assert_is_fragment(response)

    def test_case_insensitive_html_check(self) -> None:
        response = Response(body="<HTML><BODY>loud</BODY></HTML>", status=200)
        with pytest.raises(AssertionError, match="full page"):
            assert_is_fragment(response)


class TestAssertFragmentContains:
    """assert_fragment_contains checks for text in response body."""

    def test_passes_when_text_present(self) -> None:
        response = Response(body='<div id="results">alpha</div>')
        assert_fragment_contains(response, "alpha")

    def test_fails_when_text_absent(self) -> None:
        response = Response(body='<div id="results">alpha</div>')
        with pytest.raises(AssertionError, match="does not contain"):
            assert_fragment_contains(response, "beta")

    def test_includes_body_in_error(self) -> None:
        response = Response(body="<div>content</div>")
        with pytest.raises(AssertionError, match="content"):
            assert_fragment_contains(response, "missing")


class TestAssertFragmentNotContains:
    """assert_fragment_not_contains checks text is absent."""

    def test_passes_when_text_absent(self) -> None:
        response = Response(body='<div id="results">alpha</div>')
        assert_fragment_not_contains(response, "beta")

    def test_fails_when_text_present(self) -> None:
        response = Response(body='<div id="results">alpha</div>')
        with pytest.raises(AssertionError, match="unexpectedly contains"):
            assert_fragment_not_contains(response, "alpha")


class TestAssertIsErrorFragment:
    """assert_is_error_fragment checks for chirp error fragment markup."""

    def test_passes_for_error_fragment(self) -> None:
        body = '<div class="chirp-error" data-status="404">Not Found</div>'
        response = Response(body=body, status=404)
        assert_is_error_fragment(response, status=404)

    def test_passes_without_status_check(self) -> None:
        body = '<div class="chirp-error" data-status="500">Error</div>'
        response = Response(body=body, status=500)
        assert_is_error_fragment(response)

    def test_fails_for_non_error_fragment(self) -> None:
        response = Response(body="<div>normal content</div>", status=200)
        with pytest.raises(AssertionError, match="not a chirp error fragment"):
            assert_is_error_fragment(response)

    def test_fails_for_wrong_status(self) -> None:
        body = '<div class="chirp-error" data-status="404">Not Found</div>'
        response = Response(body=body, status=404)
        with pytest.raises(AssertionError, match="Expected status 500"):
            assert_is_error_fragment(response, status=500)

    def test_fails_for_mismatched_data_status(self) -> None:
        body = '<div class="chirp-error" data-status="404">Not Found</div>'
        response = Response(body=body, status=500)
        with pytest.raises(AssertionError, match='data-status="500"'):
            assert_is_error_fragment(response, status=500)
