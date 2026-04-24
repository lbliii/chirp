"""Tests for ``App.mount_app`` — hoist a pre-freeze sub-app into a parent."""

from pathlib import Path

import pytest

from chirp import App, AppConfig, Template
from chirp.app.mount import prefixed_path
from chirp.app.state import MountAppSkip
from chirp.contracts import check_hypermedia_surface
from chirp.contracts.types import Severity
from chirp.errors import ConfigurationError
from chirp.testing import TestClient


def _build_console_app() -> App:
    sub = App(AppConfig(debug=False, skip_contract_checks=True))

    @sub.route("/", name="console.home")
    async def home(request):  # type: ignore[no-untyped-def]
        return "console home"

    @sub.route("/users/{user_id}")
    async def user(request, user_id):  # type: ignore[no-untyped-def]
        return f"user {user_id}"

    return sub


def _build_dashboard_app() -> App:
    parent = App(AppConfig(debug=False, skip_contract_checks=True))

    @parent.route("/")
    async def index(request):  # type: ignore[no-untyped-def]
        return "dash home"

    return parent


def test_prefixed_path_root_becomes_prefix() -> None:
    assert prefixed_path("/", "/console") == "/console"


def test_prefixed_path_nonroot() -> None:
    assert prefixed_path("/users/{user_id}", "/console") == "/console/users/{user_id}"


def test_disjoint_routes_mount_cleanly() -> None:
    parent = _build_dashboard_app()
    sub = _build_console_app()
    parent.mount_app("/console", sub)
    parent.freeze()

    paths = {r.path for r in parent._runtime_state.router.routes}
    assert "/" in paths
    assert "/console" in paths
    assert "/console/users/{user_id}" in paths


async def test_mounted_routes_are_reachable() -> None:
    parent = _build_dashboard_app()
    sub = _build_console_app()
    parent.mount_app("/console", sub)

    async with TestClient(parent) as client:
        r = await client.get("/")
        assert r.status == 200
        assert r.text == "dash home"
        r = await client.get("/console")
        assert r.status == 200
        assert r.text == "console home"
        r = await client.get("/console/users/42")
        assert r.status == 200
        assert r.text == "user 42"


def test_mount_at_root_rejected() -> None:
    parent = _build_dashboard_app()
    sub = _build_console_app()
    with pytest.raises(ConfigurationError, match="non-root path"):
        parent.mount_app("/", sub)


def test_mount_at_empty_string_rejected() -> None:
    parent = _build_dashboard_app()
    sub = _build_console_app()
    with pytest.raises(ConfigurationError, match="non-root path"):
        parent.mount_app("", sub)


def test_mount_app_rejects_non_app() -> None:
    parent = _build_dashboard_app()
    with pytest.raises(ConfigurationError, match=r"chirp\.App"):
        parent.mount_app("/x", object())  # type: ignore[arg-type]


def test_mount_app_rejects_self() -> None:
    parent = _build_dashboard_app()
    with pytest.raises(ConfigurationError, match="into itself"):
        parent.mount_app("/x", parent)


def test_duplicate_route_after_prefix_fails_at_freeze() -> None:
    parent = App(AppConfig(debug=False, skip_contract_checks=True))

    @parent.route("/console")
    async def shadow(request):  # type: ignore[no-untyped-def]
        return "shadow"

    sub = App(AppConfig(debug=False, skip_contract_checks=True))

    @sub.route("/")
    async def home(request):  # type: ignore[no-untyped-def]
        return "console home"

    parent.mount_app("/console", sub)
    with pytest.raises((ConfigurationError, Exception)):
        parent.freeze()


def test_consumed_sub_app_cannot_freeze() -> None:
    parent = _build_dashboard_app()
    sub = _build_console_app()
    parent.mount_app("/console", sub)

    with pytest.raises(RuntimeError, match="consumed by mount_app"):
        sub.freeze()


def test_consumed_sub_app_cannot_mount_again() -> None:
    parent = _build_dashboard_app()
    other = _build_dashboard_app()
    sub = _build_console_app()
    parent.mount_app("/console", sub)

    with pytest.raises(ConfigurationError, match="already consumed"):
        other.mount_app("/console", sub)


def test_sub_app_middleware_runs_for_prefix_requests() -> None:
    parent = _build_dashboard_app()
    sub = _build_console_app()

    trace: list[str] = []

    class Trace:
        async def __call__(self, request, call_next):  # type: ignore[no-untyped-def]
            trace.append(request.path)
            return await call_next(request)

    sub.add_middleware(Trace())
    parent.mount_app("/console", sub)

    import asyncio

    async def _run() -> None:
        async with TestClient(parent) as client:
            await client.get("/console")
            await client.get("/console/users/7")

    asyncio.run(_run())
    assert "/console" in trace
    assert "/console/users/7" in trace


def test_sub_app_template_globals_merge(tmp_path: Path) -> None:
    tpl_dir = tmp_path / "tpl"
    tpl_dir.mkdir()
    (tpl_dir / "probe.html").write_text("{{ console_theme() }}")

    parent = App(AppConfig(template_dir=str(tpl_dir), debug=False, skip_contract_checks=True))

    @parent.route("/")
    async def home(request):  # type: ignore[no-untyped-def]
        return Template("probe.html")

    sub = App(AppConfig(debug=False, skip_contract_checks=True))
    sub.template_global("console_theme")(lambda: "dark")

    parent.mount_app("/console", sub)
    parent.freeze()

    rendered = parent._kida_env.get_template("probe.html").render({})
    assert rendered == "dark"


def test_template_global_collision_parent_wins(tmp_path: Path) -> None:
    parent = App(AppConfig(template_dir=str(tmp_path), debug=False, skip_contract_checks=True))
    parent.template_global("theme")(lambda: "parent-wins")

    sub = App(AppConfig(debug=False, skip_contract_checks=True))
    sub.template_global("theme")(lambda: "sub-loses")

    parent.mount_app("/console", sub)
    parent.freeze()

    # Parent's registration won
    assert parent._mutable_state.template_globals["theme"]() == "parent-wins"

    # INFO contract issue was recorded in category mount_app_merge
    result = check_hypermedia_surface(parent)
    issues = [i for i in result.issues if i.category == "mount_app_merge"]
    assert issues
    assert issues[0].severity == Severity.INFO
    assert "theme" in issues[0].message
    assert "/console" in issues[0].message


def test_sub_app_startup_hooks_merge_into_parent() -> None:
    parent = _build_dashboard_app()
    sub = _build_console_app()

    fired: list[str] = []

    @parent.on_startup
    async def parent_hook():  # type: ignore[no-untyped-def]
        fired.append("parent")

    @sub.on_startup
    async def sub_hook():  # type: ignore[no-untyped-def]
        fired.append("sub")

    parent.mount_app("/console", sub)
    parent.freeze()

    # Both hooks present, parent first (registered before hoist)
    assert parent._mutable_state.startup_hooks == [parent_hook, sub_hook]


def test_mount_app_rejects_sub_app_with_mount_pages(tmp_path: Path) -> None:
    pages_dir = tmp_path / "pages"
    pages_dir.mkdir()
    (pages_dir / "page.py").write_text("def get(): return {}")
    (pages_dir / "page.html").write_text("<html></html>")

    sub = App(AppConfig(template_dir=str(pages_dir), debug=False, skip_contract_checks=True))
    sub.mount_pages(str(pages_dir))

    parent = _build_dashboard_app()
    with pytest.raises(ConfigurationError, match="deep page/shell state"):
        parent.mount_app("/console", sub)


def test_mount_app_cannot_run_after_parent_frozen() -> None:
    parent = _build_dashboard_app()
    parent.freeze()
    sub = _build_console_app()
    with pytest.raises(RuntimeError):
        parent.mount_app("/console", sub)


def test_route_name_collision_surfaces_via_existing_check() -> None:
    parent = App(AppConfig(debug=False, skip_contract_checks=True))

    @parent.route("/home", name="home")
    async def parent_home(request):  # type: ignore[no-untyped-def]
        return "parent"

    sub = App(AppConfig(debug=False, skip_contract_checks=True))

    @sub.route("/other", name="home")
    async def sub_home(request):  # type: ignore[no-untyped-def]
        return "sub"

    parent.mount_app("/console", sub)
    parent.freeze()

    issues = [i for i in check_hypermedia_surface(parent).issues if i.category == "route_names"]
    assert issues
    assert issues[0].severity == Severity.ERROR


def test_mount_app_skip_dataclass_is_frozen() -> None:
    skip = MountAppSkip("template_global", "theme", "/console")
    with pytest.raises((AttributeError, Exception)):
        skip.key = "other"  # type: ignore[misc]
