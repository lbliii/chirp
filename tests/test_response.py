"""Tests for chirp.http.response — Response chaining and Redirect."""

import pytest

from chirp.http.response import Redirect, Response, SSEResponse


class TestResponse:
    def test_defaults(self) -> None:
        r = Response()
        assert r.body == ""
        assert r.status == 200
        assert r.content_type == "text/html; charset=utf-8"
        assert r.headers == ()
        assert r.cookies == ()

    def test_with_status(self) -> None:
        r = Response().with_status(201)
        assert r.status == 201

    def test_with_header(self) -> None:
        r = Response().with_header("X-Custom", "value")
        assert r.headers == (("X-Custom", "value"),)

    def test_chained_headers(self) -> None:
        r = Response().with_header("A", "1").with_header("B", "2")
        assert r.headers == (("A", "1"), ("B", "2"))

    def test_with_headers_dict(self) -> None:
        r = Response().with_headers({"A": "1", "B": "2"})
        assert ("A", "1") in r.headers
        assert ("B", "2") in r.headers

    def test_with_content_type(self) -> None:
        r = Response().with_content_type("application/json")
        assert r.content_type == "application/json"

    def test_with_cookie(self) -> None:
        r = Response().with_cookie("session", "abc123")
        assert len(r.cookies) == 1
        assert r.cookies[0].name == "session"
        assert r.cookies[0].value == "abc123"

    def test_without_cookie(self) -> None:
        r = Response().without_cookie("session")
        assert len(r.cookies) == 1
        assert r.cookies[0].name == "session"
        assert r.cookies[0].max_age == 0

    def test_chaining_returns_new_objects(self) -> None:
        r1 = Response("hello")
        r2 = r1.with_status(201)
        r3 = r2.with_header("X-Foo", "bar")

        assert r1.status == 200
        assert r2.status == 201
        assert r2.headers == ()
        assert r3.headers == (("X-Foo", "bar"),)

    def test_body_bytes_from_str(self) -> None:
        r = Response(body="hello")
        assert r.body_bytes == b"hello"

    def test_body_bytes_from_bytes(self) -> None:
        r = Response(body=b"hello")
        assert r.body_bytes == b"hello"

    def test_text_from_str(self) -> None:
        r = Response(body="hello")
        assert r.text == "hello"

    def test_text_from_bytes(self) -> None:
        r = Response(body=b"hello")
        assert r.text == "hello"

    def test_frozen(self) -> None:
        r = Response()
        with pytest.raises(AttributeError):
            r.status = 404  # type: ignore[misc]

    def test_full_chain(self) -> None:
        r = (
            Response("Created")
            .with_status(201)
            .with_header("Location", "/users/42")
            .with_cookie("session", "tok", secure=True)
        )
        assert r.body == "Created"
        assert r.status == 201
        assert r.headers == (("Location", "/users/42"),)
        assert r.cookies[0].secure is True


class TestHtmxResponseHeaders:
    """Tests for .with_hx_*() chainable htmx response header helpers."""

    def test_hx_redirect(self) -> None:
        r = Response().with_hx_redirect("/dashboard")
        assert ("HX-Redirect", "/dashboard") in r.headers

    def test_hx_location_simple(self) -> None:
        r = Response().with_hx_location("/new-page")
        assert ("HX-Location", "/new-page") in r.headers

    def test_hx_location_with_target(self) -> None:
        r = Response().with_hx_location("/page", target="#main")
        header = r.header("HX-Location")
        import json
        obj = json.loads(header)
        assert obj["path"] == "/page"
        assert obj["target"] == "#main"

    def test_hx_location_with_all_options(self) -> None:
        r = Response().with_hx_location(
            "/page", target="#content", swap="innerHTML", source="#trigger"
        )
        header = r.header("HX-Location")
        import json
        obj = json.loads(header)
        assert obj == {
            "path": "/page",
            "target": "#content",
            "swap": "innerHTML",
            "source": "#trigger",
        }

    def test_hx_retarget(self) -> None:
        r = Response().with_hx_retarget("#errors")
        assert ("HX-Retarget", "#errors") in r.headers

    def test_hx_reswap(self) -> None:
        r = Response().with_hx_reswap("innerHTML")
        assert ("HX-Reswap", "innerHTML") in r.headers

    def test_hx_reselect(self) -> None:
        r = Response().with_hx_reselect("#content")
        assert ("HX-Reselect", "#content") in r.headers

    def test_hx_reselect_css_selector(self) -> None:
        r = Response().with_hx_reselect(".results > .item")
        assert ("HX-Reselect", ".results > .item") in r.headers

    def test_hx_trigger_string(self) -> None:
        r = Response().with_hx_trigger("closeModal")
        assert ("HX-Trigger", "closeModal") in r.headers

    def test_hx_trigger_dict(self) -> None:
        r = Response().with_hx_trigger({"showToast": {"message": "Saved!"}})
        header = r.header("HX-Trigger")
        import json
        obj = json.loads(header)
        assert obj == {"showToast": {"message": "Saved!"}}

    def test_hx_trigger_after_settle_string(self) -> None:
        r = Response().with_hx_trigger_after_settle("highlight")
        assert ("HX-Trigger-After-Settle", "highlight") in r.headers

    def test_hx_trigger_after_settle_dict(self) -> None:
        r = Response().with_hx_trigger_after_settle({"flash": {"level": "info"}})
        header = r.header("HX-Trigger-After-Settle")
        import json
        assert json.loads(header) == {"flash": {"level": "info"}}

    def test_hx_trigger_after_swap_string(self) -> None:
        r = Response().with_hx_trigger_after_swap("scrollTop")
        assert ("HX-Trigger-After-Swap", "scrollTop") in r.headers

    def test_hx_trigger_after_swap_dict(self) -> None:
        r = Response().with_hx_trigger_after_swap({"animate": True})
        header = r.header("HX-Trigger-After-Swap")
        import json
        assert json.loads(header) == {"animate": True}

    def test_hx_push_url_string(self) -> None:
        r = Response().with_hx_push_url("/new-url")
        assert ("HX-Push-Url", "/new-url") in r.headers

    def test_hx_push_url_false(self) -> None:
        r = Response().with_hx_push_url(False)
        assert ("HX-Push-Url", "false") in r.headers

    def test_hx_push_url_true(self) -> None:
        r = Response().with_hx_push_url(True)
        assert ("HX-Push-Url", "true") in r.headers

    def test_hx_replace_url_string(self) -> None:
        r = Response().with_hx_replace_url("/replaced")
        assert ("HX-Replace-Url", "/replaced") in r.headers

    def test_hx_replace_url_false(self) -> None:
        r = Response().with_hx_replace_url(False)
        assert ("HX-Replace-Url", "false") in r.headers

    def test_hx_refresh(self) -> None:
        r = Response().with_hx_refresh()
        assert ("HX-Refresh", "true") in r.headers

    def test_chaining_multiple_hx_headers(self) -> None:
        r = (
            Response(body="<div>errors</div>")
            .with_status(422)
            .with_hx_retarget("#form-errors")
            .with_hx_reswap("innerHTML")
            .with_hx_trigger("validationFailed")
        )
        assert r.status == 422
        assert r.header("HX-Retarget") == "#form-errors"
        assert r.header("HX-Reswap") == "innerHTML"
        assert r.header("HX-Trigger") == "validationFailed"

    def test_immutability_preserved(self) -> None:
        r1 = Response(body="ok")
        r2 = r1.with_hx_redirect("/home")
        assert r1.headers == ()
        assert ("HX-Redirect", "/home") in r2.headers


class TestSSEResponse:
    """SSEResponse no-op surface must cover every with_*/without_* on Response."""

    def test_sse_returns_self_for_all_noop_methods(self) -> None:
        """Every no-op method returns the same SSEResponse instance."""
        sse = SSEResponse(event_stream=None)
        assert sse.with_status(200) is sse
        assert sse.with_header("X-Foo", "bar") is sse
        assert sse.with_headers({"A": "1"}) is sse
        assert sse.with_content_type("text/plain") is sse
        assert sse.with_cookie("name", "val") is sse
        assert sse.without_cookie("name") is sse
        assert sse.with_hx_redirect("/url") is sse
        assert sse.with_hx_location("/url") is sse
        assert sse.with_hx_location("/url", target="#t", swap="innerHTML") is sse
        assert sse.with_hx_retarget("#sel") is sse
        assert sse.with_hx_reswap("outerHTML") is sse
        assert sse.with_hx_reselect("#sel") is sse
        assert sse.with_hx_trigger("evt") is sse
        assert sse.with_hx_trigger({"a": 1}) is sse
        assert sse.with_hx_trigger_after_settle("evt") is sse
        assert sse.with_hx_trigger_after_swap("evt") is sse
        assert sse.with_hx_push_url("/url") is sse
        assert sse.with_hx_push_url(False) is sse
        assert sse.with_hx_replace_url("/url") is sse
        assert sse.with_hx_replace_url(False) is sse
        assert sse.with_hx_refresh() is sse

    def test_sse_covers_all_response_with_methods(self) -> None:
        """SSEResponse has a no-op for every with_*/without_* method on Response.

        This test auto-detects new methods added to Response, so drift
        between the two classes is caught immediately.
        """
        response_methods = {
            name
            for name in dir(Response)
            if (name.startswith(("with_", "without_")))
            and callable(getattr(Response, name))
        }
        sse_methods = {
            name
            for name in dir(SSEResponse)
            if (name.startswith(("with_", "without_")))
            and callable(getattr(SSEResponse, name))
        }
        missing = response_methods - sse_methods
        assert not missing, (
            f"SSEResponse is missing no-op methods for: {sorted(missing)}. "
            f"Add them to SSEResponse so middleware chains don't crash."
        )


class TestRedirect:
    def test_defaults(self) -> None:
        r = Redirect("/login")
        assert r.url == "/login"
        assert r.status == 302
        assert r.headers == ()

    def test_custom_status(self) -> None:
        r = Redirect("/new-url", status=301)
        assert r.status == 301

    def test_frozen(self) -> None:
        r = Redirect("/login")
        with pytest.raises(AttributeError):
            r.url = "/other"  # type: ignore[misc]
