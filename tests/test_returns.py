"""Tests for chirp.templating.returns — Template, Fragment, Page, Stream, ValidationError, OOB."""

import pytest

from chirp.templating.returns import OOB, Fragment, Page, Stream, Template, ValidationError


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

    def test_target_default_none(self) -> None:
        f = Fragment("search.html", "results_list")
        assert f.target is None

    def test_target_explicit(self) -> None:
        f = Fragment("cart.html", "counter", target="cart-counter", count=5)
        assert f.target == "cart-counter"
        assert f.context == {"count": 5}

    def test_target_frozen(self) -> None:
        f = Fragment("a.html", "b", target="x")
        with pytest.raises(AttributeError):
            f.target = "y"  # type: ignore[misc]


class TestValidationError:
    def test_basic(self) -> None:
        ve = ValidationError("form.html", "form_body", errors={"email": ["Required"]})
        assert ve.template_name == "form.html"
        assert ve.block_name == "form_body"
        assert ve.retarget is None
        assert ve.context == {"errors": {"email": ["Required"]}}

    def test_with_retarget(self) -> None:
        ve = ValidationError("form.html", "form_body", retarget="#errors", errors={})
        assert ve.retarget == "#errors"
        assert ve.context == {"errors": {}}

    def test_multiple_context_kwargs(self) -> None:
        ve = ValidationError(
            "form.html",
            "form_body",
            errors={"name": ["Too short"]},
            form={"name": "x"},
        )
        assert ve.context == {"errors": {"name": ["Too short"]}, "form": {"name": "x"}}

    def test_frozen(self) -> None:
        ve = ValidationError("form.html", "form_body", errors={})
        with pytest.raises(AttributeError):
            ve.retarget = "#new"  # type: ignore[misc]


class TestOOB:
    def test_basic(self) -> None:
        main = Fragment("search.html", "results_list")
        oob1 = Fragment("cart.html", "counter")
        oob2 = Fragment("cart.html", "summary")
        oob = OOB(main, oob1, oob2)
        assert oob.main is main
        assert oob.oob_fragments == (oob1, oob2)

    def test_with_template_main(self) -> None:
        main = Template("page.html")
        oob = OOB(main, Fragment("cart.html", "counter"))
        assert oob.main is main

    def test_with_page_main(self) -> None:
        main = Page("page.html", "content")
        oob = OOB(main, Fragment("cart.html", "counter"))
        assert oob.main is main

    def test_zero_oob_fragments(self) -> None:
        main = Fragment("search.html", "results_list")
        oob = OOB(main)
        assert oob.oob_fragments == ()

    def test_frozen(self) -> None:
        oob = OOB(Fragment("a.html", "b"))
        with pytest.raises(AttributeError):
            oob.main = Fragment("c.html", "d")  # type: ignore[misc]


class TestTopLevelImports:
    """New return types are importable from the top-level chirp package."""

    def test_import_validation_error(self) -> None:
        import chirp

        assert chirp.ValidationError is ValidationError

    def test_import_oob(self) -> None:
        import chirp

        assert chirp.OOB is OOB


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
