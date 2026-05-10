"""Tests for app.url_for and the url_for template global."""

from dataclasses import replace
from pathlib import Path

import pytest

from chirp import App, AppConfig, Redirect, Template
from chirp.contracts import check_hypermedia_surface
from chirp.contracts.types import Severity
from chirp.testing import TestClient


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


def test_url_for_rejects_value_that_does_not_match_converter(tmp_path: Path) -> None:
    pages_dir = tmp_path / "pages"
    _write_page(
        pages_dir / "contacts" / "{contact_id:int}",
        body="def get(contact_id: int): return {}",
    )
    app = _app_with_pages(pages_dir)

    with pytest.raises(ValueError, match="does not match converter 'int'"):
        app.url_for("contacts.contact_id", contact_id="alice")


def test_url_for_path_converter_requires_non_empty_value(tmp_path: Path) -> None:
    pages_dir = tmp_path / "pages"
    _write_page(
        pages_dir / "files" / "{filepath:path}",
        body="def get(filepath: str): return {}",
    )
    app = _app_with_pages(pages_dir)

    with pytest.raises(ValueError, match="does not match converter 'path'"):
        app.url_for("files.filepath", filepath="")


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


async def _tenant_scope_middleware(request, next_handler):  # type: ignore[no-untyped-def]
    if request.path == "/c/acme" or request.path.startswith("/c/acme/"):
        local_path = request.path.removeprefix("/c/acme") or "/"
        request = replace(request, path=local_path).with_url_scope("/c/acme")
    return await next_handler(request)


@pytest.mark.asyncio
async def test_request_url_for_scopes_template_links_htmx_fragments_and_sse(
    tmp_path: Path,
) -> None:
    tpl_dir = tmp_path / "templates"
    tpl_dir.mkdir()
    (tpl_dir / "links.html").write_text(
        """
<a id="board-link" href="{{ url_for('boards.detail', board_id='ic', tab='cast') }}">board</a>
<a id="boosted" hx-get="{{ url_for('boards.detail', board_id='ic') }}">boost</a>
<a id="fragment" hx-get="{{ fragment_url(url_for('boards.detail', board_id='ic'), 'content') }}">fragment</a>
<section id="events" sse-connect="{{ url_for('threads.events', thread_id=42) }}"></section>
"""
    )
    app = App(AppConfig(template_dir=str(tpl_dir), debug=False))
    app.add_middleware(_tenant_scope_middleware)

    @app.route("/", name="home")
    def home():
        return Template("links.html")

    @app.route("/boards/{board_id}", name="boards.detail")
    def board(board_id: str):
        return f"board {board_id}"

    @app.route("/threads/{thread_id}/events", name="threads.events")
    def events(thread_id: str):
        return f"events {thread_id}"

    async with TestClient(app) as client:
        response = await client.get("/c/acme/")

    assert response.status == 200
    body = response.body.decode("utf-8")
    assert 'href="/c/acme/boards/ic?tab=cast"' in body
    assert 'hx-get="/c/acme/boards/ic"' in body
    assert 'hx-get="/_frag/c/acme/boards/ic?_b=content"' in body
    assert 'sse-connect="/c/acme/threads/42/events"' in body
    assert app.url_for("boards.detail", board_id="ic") == "/boards/ic"


@pytest.mark.asyncio
async def test_request_url_for_scopes_mounted_app_routes(tmp_path: Path) -> None:
    tpl_dir = tmp_path / "templates"
    tpl_dir.mkdir()
    (tpl_dir / "console.html").write_text(
        """
<a href="{{ url_for('console.user', user_id=42) }}">user</a>
<button hx-get="{{ url_for('console.user', user_id=43) }}">next</button>
"""
    )
    parent = App(AppConfig(template_dir=str(tpl_dir), debug=False))
    parent.add_middleware(_tenant_scope_middleware)
    console = App(AppConfig(debug=False, skip_contract_checks=True))

    @console.route("/users/{user_id}", name="console.user")
    def user(user_id: str):
        return Template("console.html")

    parent.mount_app("/console", console)

    async with TestClient(parent) as client:
        response = await client.get("/c/acme/console/users/42")

    assert response.status == 200
    body = response.body.decode("utf-8")
    assert 'href="/c/acme/console/users/42"' in body
    assert 'hx-get="/c/acme/console/users/43"' in body
    assert parent.url_for("console.user", user_id=42) == "/console/users/42"


@pytest.mark.asyncio
async def test_request_scoped_url_supports_redirects(tmp_path: Path) -> None:
    tpl_dir = tmp_path / "templates"
    tpl_dir.mkdir()
    app = App(AppConfig(template_dir=str(tpl_dir), debug=False))
    app.add_middleware(_tenant_scope_middleware)

    @app.route("/jump", name="jump")
    def jump(request):
        return Redirect(request.url_for("boards.detail", board_id="ic", next="/boards/ooc"))

    @app.route("/boards/{board_id}", name="boards.detail")
    def board(board_id: str):
        return f"board {board_id}"

    async with TestClient(app) as client:
        response = await client.get("/c/acme/jump")

    assert response.status == 302
    assert ("location", "/c/acme/boards/ic?next=%2Fboards%2Fooc") in response.headers


@pytest.mark.asyncio
async def test_custom_url_for_template_global_still_wins(tmp_path: Path) -> None:
    tpl_dir = tmp_path / "templates"
    tpl_dir.mkdir()
    (tpl_dir / "links.html").write_text("{{ url_for('boards.detail', board_id='ic') }}")
    app = App(AppConfig(template_dir=str(tpl_dir), debug=False))
    app.add_middleware(_tenant_scope_middleware)

    @app.template_global("url_for")
    def custom_url_for(*args, **kwargs):  # type: ignore[no-untyped-def]
        return "OVERRIDE"

    @app.route("/", name="home")
    def home():
        return Template("links.html")

    @app.route("/boards/{board_id}", name="boards.detail")
    def board(board_id: str):
        return f"board {board_id}"

    async with TestClient(app) as client:
        response = await client.get("/c/acme/")

    assert response.body.decode("utf-8") == "OVERRIDE"
