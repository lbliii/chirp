"""Page(...) TypeError ergonomics — guided message when block_name is omitted."""

import pytest

from chirp import Page, Template


def test_page_without_block_name_raises_guided_type_error() -> None:
    with pytest.raises(TypeError) as exc:
        Page("page.html", title="Home")

    message = str(exc.value)
    assert 'Page("page.html", "' in message
    assert "Template(" in message


def test_page_with_block_name_still_constructs() -> None:
    page = Page("page.html", "content", title="Home")
    assert page.template_name == "page.html"
    assert page.block_name == "content"
    assert page.context == {"title": "Home"}


def test_page_with_page_block_name_kwarg_still_works() -> None:
    page = Page("dash.html", "results", page_block_name="page_root", stats={})
    assert page.block_name == "results"
    assert page.page_block_name == "page_root"


def test_page_no_positional_args_raises_type_error() -> None:
    with pytest.raises(TypeError):
        Page()  # type: ignore[call-arg]


def test_template_with_only_template_name_is_valid() -> None:
    tmpl = Template("page.html", title="Home")
    assert tmpl.template_name == "page.html"
    assert tmpl.context == {"title": "Home"}
