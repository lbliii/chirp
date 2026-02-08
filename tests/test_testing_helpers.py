"""Tests for chirp.testing — fragment and htmx assertion helpers."""

import pytest

from chirp.http.response import Response
from chirp.testing import (
    assert_fragment_contains,
    assert_fragment_not_contains,
    assert_hx_push_url,
    assert_hx_redirect,
    assert_hx_reswap,
    assert_hx_retarget,
    assert_hx_trigger,
    assert_is_error_fragment,
    assert_is_fragment,
    hx_headers,
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


# ---------------------------------------------------------------------------
# htmx header helpers
# ---------------------------------------------------------------------------


class TestHxHeaders:
    """hx_headers() extracts HX-* response headers into a dict."""

    def test_extracts_hx_headers(self) -> None:
        r = Response().with_hx_redirect("/home").with_header("X-Custom", "val")
        result = hx_headers(r)
        assert result == {"HX-Redirect": "/home"}
        assert "X-Custom" not in result

    def test_empty_when_no_hx_headers(self) -> None:
        r = Response().with_header("Content-Type", "text/plain")
        assert hx_headers(r) == {}

    def test_multiple_hx_headers(self) -> None:
        r = (
            Response()
            .with_hx_retarget("#errors")
            .with_hx_reswap("innerHTML")
            .with_hx_trigger("flash")
        )
        result = hx_headers(r)
        assert result["HX-Retarget"] == "#errors"
        assert result["HX-Reswap"] == "innerHTML"
        assert result["HX-Trigger"] == "flash"


class TestAssertHxRedirect:
    """assert_hx_redirect checks HX-Redirect header."""

    def test_passes(self) -> None:
        r = Response().with_hx_redirect("/dashboard")
        assert_hx_redirect(r, "/dashboard")

    def test_fails_when_missing(self) -> None:
        r = Response()
        with pytest.raises(AssertionError, match="no HX-Redirect"):
            assert_hx_redirect(r, "/dashboard")

    def test_fails_when_wrong_url(self) -> None:
        r = Response().with_hx_redirect("/wrong")
        with pytest.raises(AssertionError, match="/dashboard"):
            assert_hx_redirect(r, "/dashboard")


class TestAssertHxTrigger:
    """assert_hx_trigger checks HX-Trigger header variants."""

    def test_string_event(self) -> None:
        r = Response().with_hx_trigger("closeModal")
        assert_hx_trigger(r, "closeModal")

    def test_dict_event(self) -> None:
        r = Response().with_hx_trigger({"showToast": {"msg": "ok"}})
        assert_hx_trigger(r, {"showToast": {"msg": "ok"}})

    def test_event_name_in_json(self) -> None:
        r = Response().with_hx_trigger({"closeModal": True})
        assert_hx_trigger(r, "closeModal")

    def test_after_settle(self) -> None:
        r = Response().with_hx_trigger_after_settle("highlight")
        assert_hx_trigger(r, "highlight", after="settle")

    def test_after_swap(self) -> None:
        r = Response().with_hx_trigger_after_swap("scrollTop")
        assert_hx_trigger(r, "scrollTop", after="swap")

    def test_fails_when_missing(self) -> None:
        r = Response()
        with pytest.raises(AssertionError, match="no HX-Trigger"):
            assert_hx_trigger(r, "nope")


class TestAssertHxRetarget:
    """assert_hx_retarget checks HX-Retarget header."""

    def test_passes(self) -> None:
        r = Response().with_hx_retarget("#errors")
        assert_hx_retarget(r, "#errors")

    def test_fails_when_missing(self) -> None:
        r = Response()
        with pytest.raises(AssertionError, match="no HX-Retarget"):
            assert_hx_retarget(r, "#errors")

    def test_fails_when_wrong_selector(self) -> None:
        r = Response().with_hx_retarget("#other")
        with pytest.raises(AssertionError, match="#errors"):
            assert_hx_retarget(r, "#errors")


class TestAssertHxReswap:
    """assert_hx_reswap checks HX-Reswap header."""

    def test_passes(self) -> None:
        r = Response().with_hx_reswap("innerHTML")
        assert_hx_reswap(r, "innerHTML")

    def test_fails_when_missing(self) -> None:
        r = Response()
        with pytest.raises(AssertionError, match="no HX-Reswap"):
            assert_hx_reswap(r, "innerHTML")


class TestAssertHxPushUrl:
    """assert_hx_push_url checks HX-Push-Url header."""

    def test_passes_with_url(self) -> None:
        r = Response().with_hx_push_url("/new")
        assert_hx_push_url(r, "/new")

    def test_passes_with_false(self) -> None:
        r = Response().with_hx_push_url(False)
        assert_hx_push_url(r, "false")

    def test_fails_when_missing(self) -> None:
        r = Response()
        with pytest.raises(AssertionError, match="no HX-Push-Url"):
            assert_hx_push_url(r, "/new")
