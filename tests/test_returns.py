"""Tests for chirp.templating.returns — Template, Fragment, Stream."""

import pytest

from chirp.templating.returns import Fragment, Stream, Template


class TestTemplate:
    def test_basic(self) -> None:
        t = Template("page.html", title="Home")
        assert t.name == "page.html"
        assert t.context == {"title": "Home"}

    def test_no_context(self) -> None:
        t = Template("page.html")
        assert t.context == {}

    def test_multiple_kwargs(self) -> None:
        t = Template("page.html", title="Home", items=[1, 2, 3])
        assert t.context == {"title": "Home", "items": [1, 2, 3]}

    def test_frozen(self) -> None:
        t = Template("page.html")
        with pytest.raises(AttributeError):
            t.name = "other.html"  # type: ignore[misc]


class TestFragment:
    def test_basic(self) -> None:
        f = Fragment("search.html", "results_list", results=[1, 2])
        assert f.template_name == "search.html"
        assert f.block_name == "results_list"
        assert f.context == {"results": [1, 2]}

    def test_no_context(self) -> None:
        f = Fragment("search.html", "results_list")
        assert f.context == {}

    def test_frozen(self) -> None:
        f = Fragment("a.html", "b")
        with pytest.raises(AttributeError):
            f.block_name = "other"  # type: ignore[misc]


class TestStream:
    def test_basic(self) -> None:
        s = Stream("dashboard.html", stats="loaded")
        assert s.template_name == "dashboard.html"
        assert s.context == {"stats": "loaded"}

    def test_no_context(self) -> None:
        s = Stream("dashboard.html")
        assert s.context == {}

    def test_frozen(self) -> None:
        s = Stream("dashboard.html")
        with pytest.raises(AttributeError):
            s.template_name = "other.html"  # type: ignore[misc]
