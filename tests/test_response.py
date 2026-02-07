"""Tests for chirp.http.response — Response chaining and Redirect."""

import pytest

from chirp.http.response import Redirect, Response


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
