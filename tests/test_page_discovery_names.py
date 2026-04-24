"""Tests for default and overridden route names in page discovery."""

from pathlib import Path

from chirp.pages.discovery import default_route_name, discover_pages


def test_default_route_name_for_root() -> None:
    assert default_route_name("/") == "index"


def test_default_route_name_single_segment() -> None:
    assert default_route_name("/about") == "about"


def test_default_route_name_multi_segment() -> None:
    assert default_route_name("/a/b/c") == "a.b.c"


def test_default_route_name_with_param() -> None:
    assert default_route_name("/contacts/{contact_id}") == "contacts.contact_id"


def test_default_route_name_with_typed_param() -> None:
    assert default_route_name("/users/{id:int}") == "users.id"


def test_default_route_name_with_path_converter() -> None:
    assert default_route_name("/files/{path:path}") == "files.path"


def test_default_route_name_mixed_static_and_param() -> None:
    assert default_route_name("/projects/{slug}/settings") == "projects.slug.settings"


def _write_page(dir_: Path, body: str = "def get(): return {}") -> None:
    dir_.mkdir(parents=True, exist_ok=True)
    (dir_ / "page.py").write_text(body)
    (dir_ / "page.html").write_text("<html></html>")


def test_discovered_root_page_has_name_index(tmp_path: Path) -> None:
    pages_dir = tmp_path / "pages"
    _write_page(pages_dir)

    routes = discover_pages(pages_dir)
    assert len(routes) == 1
    assert routes[0].name == "index"


def test_discovered_static_page_name(tmp_path: Path) -> None:
    pages_dir = tmp_path / "pages"
    _write_page(pages_dir / "contacts")

    routes = discover_pages(pages_dir)
    names = {r.name for r in routes}
    assert "contacts" in names


def test_discovered_parametric_page_name(tmp_path: Path) -> None:
    pages_dir = tmp_path / "pages"
    _write_page(pages_dir / "contacts" / "{contact_id}")

    routes = discover_pages(pages_dir)
    names = {r.name for r in routes}
    assert "contacts.contact_id" in names


def test_discovered_deeply_parametric_page_name(tmp_path: Path) -> None:
    pages_dir = tmp_path / "pages"
    _write_page(pages_dir / "projects" / "{slug}" / "settings")

    routes = discover_pages(pages_dir)
    names = {r.name for r in routes}
    assert "projects.slug.settings" in names


def test_module_level_name_override(tmp_path: Path) -> None:
    pages_dir = tmp_path / "pages"
    _write_page(
        pages_dir / "contacts" / "{contact_id}",
        body='name = "contact.detail"\n\ndef get(contact_id): return {}',
    )

    routes = discover_pages(pages_dir)
    names = {r.name for r in routes}
    assert "contact.detail" in names
    assert "contacts.contact_id" not in names


def test_module_level_name_empty_string_falls_back_to_default(tmp_path: Path) -> None:
    pages_dir = tmp_path / "pages"
    _write_page(
        pages_dir / "contacts",
        body='name = ""\n\ndef get(): return {}',
    )

    routes = discover_pages(pages_dir)
    names = {r.name for r in routes}
    assert "contacts" in names
