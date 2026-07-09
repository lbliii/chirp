"""Boosted shell-outlet navigation contracts."""

from pathlib import Path

import pytest

from chirp import App, AppConfig, Template, use_chirp_ui
from chirp.contracts import check_hypermedia_surface
from chirp.testing import RouteSmokeCase, TestClient, assert_route_smoke


def _write_shell_outlet_app(
    pages: Path,
    *,
    outlet: bool = True,
    outlet_mode: str | None = None,
    include_page_content_wrapper: bool = False,
) -> None:
    pages.mkdir()
    outlet_comment = "{# outlet: main #}\n" if outlet else ""
    outlet_mode_comment = f"{{# outlet_mode: {outlet_mode} #}}\n" if outlet_mode else ""
    (pages / "_layout.html").write_text(
        "{# target: body #}\n"
        f"{outlet_comment}"
        f"{outlet_mode_comment}"
        "<!DOCTYPE html><html><body>"
        '<main id="main" hx-boost="true" hx-target="#main" '
        'hx-swap="innerHTML" hx-select="#page-content">'
        '<div id="page-content">{% block content %}{% end %}</div>'
        "</main>"
        "</body></html>",
        encoding="utf-8",
    )
    (pages / "page.py").write_text(
        "from chirp import Page\n\n"
        "def get():\n"
        '    return Page("page.html", "page_content", page_block_name="page_root", '
        'message="Ready")\n',
        encoding="utf-8",
    )
    wrapper_start = '<div id="page-content">' if include_page_content_wrapper else ""
    wrapper_end = "</div>" if include_page_content_wrapper else ""
    (pages / "page.html").write_text(
        '{% block page_root %}<div id="page-root">'
        f"{wrapper_start}"
        "{% block page_root_inner %}"
        "{% block page_content %}<p>{{ message }}</p>{% end %}"
        "{% end %}"
        f"{wrapper_end}"
        "</div>{% end %}",
        encoding="utf-8",
    )


@pytest.mark.asyncio
@pytest.mark.issue(497)
@pytest.mark.issue(546)
async def test_boosted_navigation_to_shell_outlet_includes_selectable_page_content(
    tmp_path: Path,
) -> None:
    pages = tmp_path / "pages"
    _write_shell_outlet_app(pages)

    app = App(AppConfig(template_dir=str(pages)))
    app.register_fragment_target("main", fragment_block="page_root", scope_name="shell")
    app.register_swap_scope("shell", "main")
    app.mount_pages(str(pages))
    check = check_hypermedia_surface(app)

    async with TestClient(app) as client:
        responses = await assert_route_smoke(
            client,
            [
                RouteSmokeCase(
                    "/",
                    mode="boosted",
                    template="page.html",
                    block="page_root",
                    target="main",
                )
            ],
        )
        response = responses[("/", "boosted")]
        htmx4_response = await client.boosted(
            "/",
            target="main#main",
            source="a#sidebar-home",
            request_type="partial",
        )

    assert response.status == 200
    assert 'id="page-content"' in response.text
    assert 'id="page-root"' in response.text
    assert "Ready" in response.text
    assert htmx4_response.status == 200
    assert 'id="page-root"' in htmx4_response.text
    assert 'id="page-content"' not in htmx4_response.text
    assert "<!DOCTYPE" not in htmx4_response.text
    assert response.header("HX-Reselect") is None
    assert htmx4_response.header("HX-Reselect") is None
    assert [issue for issue in check.errors if issue.category == "layout_outlet"] == []


@pytest.mark.asyncio
@pytest.mark.issue(585)
async def test_replace_outlet_recovers_from_inherited_page_content_selection(
    tmp_path: Path,
) -> None:
    pages = tmp_path / "pages"
    _write_shell_outlet_app(pages, outlet_mode="replace")

    app = App(AppConfig(template_dir=str(pages)))
    app.register_fragment_target("main", fragment_block="page_root", scope_name="shell")
    app.register_swap_scope("shell", "main")
    app.mount_pages(str(pages))
    check = check_hypermedia_surface(app)

    async with TestClient(app) as client:
        response = await client.boosted("/", target="main")
        htmx4_response = await client.boosted(
            "/",
            target="main#main",
            source="a#sidebar-home",
            request_type="partial",
        )
        narrow = await client.fragment("/", target="main")

    assert response.status == 200
    assert 'id="page-root"' in response.text
    assert 'id="page-content"' not in response.text
    assert response.header("HX-Reselect") == "*"
    assert htmx4_response.status == 200
    assert htmx4_response.header("HX-Reselect") is None
    assert narrow.status == 200
    assert narrow.header("HX-Reselect") is None
    outlet_errors = [issue for issue in check.errors if issue.category == "layout_outlet"]
    assert len(outlet_errors) == 1
    assert "Route '/'" in outlet_errors[0].message
    assert "page_root" in outlet_errors[0].message
    assert "#page-content" in outlet_errors[0].message
    assert "#main" in outlet_errors[0].message


@pytest.mark.issue(585)
def test_replace_outlet_allows_page_fragment_with_selected_wrapper(tmp_path: Path) -> None:
    pages = tmp_path / "pages"
    _write_shell_outlet_app(
        pages,
        outlet_mode="replace",
        include_page_content_wrapper=True,
    )

    app = App(AppConfig(template_dir=str(pages)))
    app.register_fragment_target("main", fragment_block="page_root", scope_name="shell")
    app.register_swap_scope("shell", "main")
    app.mount_pages(str(pages))

    check = check_hypermedia_surface(app)

    assert [issue for issue in check.errors if issue.category == "layout_outlet"] == []


@pytest.mark.asyncio
@pytest.mark.issue(585)
async def test_registry_omitted_outlet_recovers_from_inherited_selection(tmp_path: Path) -> None:
    pages = tmp_path / "pages"
    _write_shell_outlet_app(pages)

    app = App(AppConfig(template_dir=str(pages)))
    app.register_fragment_target(
        "main",
        fragment_block="page_root",
        scope_name="shell",
        omit_outer_layouts=True,
    )
    app.register_swap_scope("shell", "main")
    app.mount_pages(str(pages))
    check = check_hypermedia_surface(app)

    async with TestClient(app) as client:
        response = await client.boosted("/", target="main")

    assert response.status == 200
    assert 'id="page-root"' in response.text
    assert 'id="page-content"' not in response.text
    assert response.header("HX-Reselect") == "*"
    outlet_errors = [issue for issue in check.errors if issue.category == "layout_outlet"]
    assert len(outlet_errors) == 1
    assert "omit_outer_layouts=True" in outlet_errors[0].message


@pytest.mark.asyncio
async def test_chirpui_app_shell_extends_infers_main_outlet_for_boosted_navigation(
    tmp_path: Path,
) -> None:
    pages = tmp_path / "pages"
    pages.mkdir()
    (pages / "_layout.html").write_text(
        '{# target: body #}\n{% extends "chirpui/app_shell_layout.html" %}\n'
        "{% block brand %}Forum{% end %}\n"
        "{% block sidebar %}<nav>Boards</nav>{% end %}\n",
        encoding="utf-8",
    )
    (pages / "page.py").write_text(
        "from chirp import Page\n\n"
        "def get():\n"
        '    return Page("page.html", "page_content", page_block_name="page_root", '
        'message="Ready")\n',
        encoding="utf-8",
    )
    (pages / "page.html").write_text(
        '{% block page_root %}<div id="page-root">'
        "{% block page_root_inner %}"
        "{% block page_content %}<p>{{ message }}</p>{% end %}"
        "{% end %}"
        "</div>{% end %}",
        encoding="utf-8",
    )

    app = App(AppConfig(template_dir=str(pages), debug=True))
    use_chirp_ui(app)
    app.mount_pages(str(pages))

    async with TestClient(app) as client:
        response = await client.boosted("/", target="main")

    assert response.status == 200
    assert 'id="page-content"' in response.text
    assert 'id="page-root"' in response.text
    assert "Ready" in response.text


@pytest.mark.asyncio
@pytest.mark.issue(497)
async def test_boosted_route_smoke_rejects_full_template_with_actionable_shape(
    tmp_path: Path,
) -> None:
    (tmp_path / "search.html").write_text(
        "<!doctype html><html lang='en'><body><main>Search</main></body></html>",
        encoding="utf-8",
    )
    app = App(AppConfig(template_dir=tmp_path))

    @app.route("/search")
    def search() -> Template:
        return Template("search.html")

    async with TestClient(app) as client:
        with pytest.raises(
            AssertionError,
            match=(
                r"path='/search', intent=boosted.*target='main'.*"
                r"observed_shape='full_document'"
            ),
        ):
            await assert_route_smoke(
                client,
                [RouteSmokeCase("/search", mode="boosted", target="main")],
            )
