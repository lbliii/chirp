"""Tests for app.url_for and the url_for template global."""

from pathlib import Path

import pytest

from chirp import App, AppConfig
from chirp.contracts import check_hypermedia_surface
from chirp.contracts.types import Severity


def _write_page(dir_: Path, body: str = "def get(): return {}") -> None:
    dir_.mkdir(parents=True, exist_ok=True)
    (dir_ / "page.py").write_text(body)
    (dir_ / "page.html").write_text("<html></html>")


def _app_with_pages(pages_dir: Path) -> App:
    app = App(AppConfig(template_dir=str(pages_dir), debug=False))
    app.mount_pages(str(pages_dir))
    app.freeze()
    return app


def test_url_for_static_route(tmp_path: Path) -> None:
    pages_dir = tmp_path / "pages"
    _write_page(pages_dir / "about")
    app = _app_with_pages(pages_dir)

    assert app.url_for("about") == "/about"


def test_url_for_root_has_index_name(tmp_path: Path) -> None:
    pages_dir = tmp_path / "pages"
    _write_page(pages_dir)
    app = _app_with_pages(pages_dir)

    assert app.url_for("index") == "/"


def test_url_for_path_param(tmp_path: Path) -> None:
    pages_dir = tmp_path / "pages"
    _write_page(
        pages_dir / "contacts" / "{contact_id}",
        body="def get(contact_id): return {}",
    )
    app = _app_with_pages(pages_dir)

    assert app.url_for("contacts.contact_id", contact_id=42) == "/contacts/42"


def test_url_for_path_param_encodes_value(tmp_path: Path) -> None:
    pages_dir = tmp_path / "pages"
    _write_page(
        pages_dir / "q" / "{term}",
        body="def get(term): return {}",
    )
    app = _app_with_pages(pages_dir)

    assert app.url_for("q.term", term="hello world/slash") == "/q/hello%20world%2Fslash"


def test_url_for_path_plus_query(tmp_path: Path) -> None:
    pages_dir = tmp_path / "pages"
    _write_page(
        pages_dir / "contacts" / "{contact_id}",
        body="def get(contact_id): return {}",
    )
    app = _app_with_pages(pages_dir)

    url = app.url_for("contacts.contact_id", contact_id=42, highlight="email", tab="activity")
    assert url == "/contacts/42?highlight=email&tab=activity"


def test_url_for_query_only_multi_value(tmp_path: Path) -> None:
    pages_dir = tmp_path / "pages"
    _write_page(pages_dir / "contacts")
    app = _app_with_pages(pages_dir)

    url = app.url_for("contacts", tag=["vip", "new"], sort="name")
    assert url == "/contacts?tag=vip&tag=new&sort=name"


def test_url_for_skips_none_query_values(tmp_path: Path) -> None:
    pages_dir = tmp_path / "pages"
    _write_page(pages_dir / "contacts")
    app = _app_with_pages(pages_dir)

    assert app.url_for("contacts", q=None) == "/contacts"
    assert app.url_for("contacts", q="alice", hint=None) == "/contacts?q=alice"


def test_url_for_unknown_name_raises_lookup_error(tmp_path: Path) -> None:
    pages_dir = tmp_path / "pages"
    _write_page(pages_dir / "contacts")
    app = _app_with_pages(pages_dir)

    with pytest.raises(LookupError) as exc:
        app.url_for("contacts.detail")
    message = str(exc.value)
    assert "contacts.detail" in message
    assert "contacts" in message  # lists known names


def test_url_for_missing_path_param_raises_key_error(tmp_path: Path) -> None:
    pages_dir = tmp_path / "pages"
    _write_page(
        pages_dir / "contacts" / "{contact_id}",
        body="def get(contact_id): return {}",
    )
    app = _app_with_pages(pages_dir)

    with pytest.raises(KeyError) as exc:
        app.url_for("contacts.contact_id")
    assert "contact_id" in str(exc.value)


def test_url_for_list_path_param_raises_type_error(tmp_path: Path) -> None:
    pages_dir = tmp_path / "pages"
    _write_page(
        pages_dir / "contacts" / "{contact_id}",
        body="def get(contact_id): return {}",
    )
    app = _app_with_pages(pages_dir)

    with pytest.raises(TypeError):
        app.url_for("contacts.contact_id", contact_id=[1, 2])


def test_same_path_different_methods_is_not_a_collision(tmp_path: Path) -> None:
    """A page with both GET (page.py) and POST (_actions.py) at the same URL
    must not be flagged as a duplicate — they're method variants of one name.
    """
    pages_dir = tmp_path / "pages"
    pages_dir.mkdir()
    (pages_dir / "page.py").write_text("def get(): return {}")
    (pages_dir / "page.html").write_text("<html></html>")
    (pages_dir / "_actions.py").write_text(
        "from chirp import Fragment\n"
        "async def create(request):\n"
        "    return Fragment('page.html', 'x')\n"
    )
    app = App(AppConfig(template_dir=str(pages_dir), debug=False))
    app.mount_pages(str(pages_dir))
    app.freeze()

    assert app.url_for("index") == "/"
    assert not app._runtime_state.route_name_collisions


def test_duplicate_route_name_fails_contract_check(tmp_path: Path) -> None:
    pages_dir = tmp_path / "pages"
    _write_page(
        pages_dir / "contacts" / "{contact_id}",
        body='name = "shared"\n\ndef get(contact_id): return {}',
    )
    _write_page(
        pages_dir / "customers" / "{customer_id}",
        body='name = "shared"\n\ndef get(customer_id): return {}',
    )
    app = App(AppConfig(template_dir=str(pages_dir), debug=True, skip_contract_checks=True))
    app.mount_pages(str(pages_dir))

    result = check_hypermedia_surface(app)
    issues = [i for i in result.issues if i.category == "route_names"]
    assert issues
    assert issues[0].severity == Severity.ERROR
    assert "shared" in (issues[0].message or "")


def test_url_for_as_template_global(tmp_path: Path) -> None:
    pages_dir = tmp_path / "pages"
    tpl_dir = pages_dir
    _write_page(
        pages_dir / "contacts" / "{contact_id}",
        body="def get(contact_id): return {}",
    )
    (pages_dir / "link.html").write_text(
        "<a href=\"{{ url_for('contacts.contact_id', contact_id=7) }}\">view</a>"
    )

    app = App(AppConfig(template_dir=str(tpl_dir), debug=False))
    app.mount_pages(str(pages_dir))
    app.freeze()

    rendered = app._kida_env.get_template("link.html").render({})
    assert rendered == '<a href="/contacts/7">view</a>'


def test_url_for_template_global_is_setdefault(tmp_path: Path) -> None:
    """A user-registered url_for wins over the built-in (setdefault semantics)."""
    pages_dir = tmp_path / "pages"
    _write_page(pages_dir / "contacts")

    app = App(AppConfig(template_dir=str(pages_dir), debug=False))

    @app.template_global("url_for")
    def my_url_for(*args, **kwargs):  # type: ignore[no-untyped-def]
        return "OVERRIDE"

    app.mount_pages(str(pages_dir))
    app.freeze()

    (pages_dir / "probe.html").write_text("{{ url_for('contacts') }}")
    rendered = app._kida_env.get_template("probe.html").render({})
    assert rendered == "OVERRIDE"
