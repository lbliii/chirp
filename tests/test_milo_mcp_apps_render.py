"""Issue #578: named Kida blocks as Milo MCP App UI resources."""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from milo import CLI, MCPAppToolMeta
from milo.mcp_apps import MCP_APPS_EXTENSION_ID, MCP_APPS_MIME_TYPE
from milo.testing import MCPClient

from chirp import App, AppConfig, ConfigurationError, Fragment, Page
from chirp.errors import BlockNotFoundError
from chirp.ext.milo import use_milo
from chirp.testing import TestClient

pytestmark = pytest.mark.issue(578)

_RESOURCE_URI = "ui://chirp/work-items/create"
_TEMPLATE = """\
{% block page_root %}
<!doctype html>
<html lang="en">
  <head><title>{{ heading }}</title></head>
  <body><h1>{{ heading }}</h1></body>
</html>
{% endblock %}

{% block create_tool %}
<main aria-labelledby="create-title">
  <h1 id="create-title">{{ heading }}</h1>
  <form><input name="title" required></form>
</main>
{% endblock %}

{% block empty_tool %}
{% endblock %}
"""


def _ui_initialize_params() -> dict[str, object]:
    return {
        "capabilities": {
            "extensions": {
                MCP_APPS_EXTENSION_ID: {"mimeTypes": [MCP_APPS_MIME_TYPE]},
            }
        }
    }


def _write_template(tmp_path: Path, source: str = _TEMPLATE) -> Path:
    templates = tmp_path / "templates"
    templates.mkdir(parents=True, exist_ok=True)
    (templates / "work_items.html").write_text(source, encoding="utf-8")
    return templates


def _build_app(
    tmp_path: Path,
    *,
    block: str = "create_tool",
    context=None,
    template_source: str = _TEMPLATE,
):
    templates = _write_template(tmp_path, template_source)
    cli = CLI(name="work-items")
    work_items = cli.group("work-items", description="Work item operations")

    app = App(AppConfig(template_dir=templates))
    adapter = use_milo(app, cli, allowlist=("work-items.create",))

    @cli.ui_resource(_RESOURCE_URI, name="Create work item")
    def create_work_item_resource() -> str:
        return adapter.render_resource("work-items.create")

    @work_items.command(
        "create",
        description="Create a work item",
        ui=MCPAppToolMeta(_RESOURCE_URI),
    )
    def create_work_item(title: str) -> dict[str, object]:
        return {"title": title, "created": True}

    if context is None:

        def context() -> dict[str, str]:
            return {"heading": "Create a work item"}

    adapter.bind(
        "work-items.create",
        template="work_items.html",
        block=block,
        context=context,
    )

    @app.route("/")
    def index() -> Page:
        return Page("work_items.html", "page_root", heading="Shared template page")

    @app.route("/create-tool")
    def create_tool_page() -> Page:
        return Page("work_items.html", "create_tool", heading="Create a work item")

    @app.route("/create-tool/fragment")
    def create_tool_fragment() -> Fragment:
        return Fragment("work_items.html", "create_tool", heading="Create a work item")

    app.freeze()
    return app, adapter, cli


def test_four_surfaces_share_one_template_contract(tmp_path: Path) -> None:
    app, adapter, cli = _build_app(tmp_path)
    binding = adapter.bindings[0]
    assert binding.template == "work_items.html"
    assert binding.block == "create_tool"

    async def _browser_and_htmx() -> tuple[str, str, str]:
        async with TestClient(app) as client:
            full = await client.get("/")
            page = await client.get("/create-tool")
            fragment = await client.fragment("/create-tool/fragment")
        return full.text, page.text, fragment.text

    full_html, page_html, fragment_html = asyncio.run(_browser_and_htmx())
    assert "Shared template page" in full_html
    assert 'id="create-title"' in page_html
    assert 'id="create-title"' in fragment_html
    assert "<!doctype html>" not in fragment_html

    resource_html = adapter.render_resource("work-items.create")
    assert resource_html == fragment_html
    assert "Create a work item" in resource_html

    mcp = MCPClient(cli)
    tool = mcp.call("work-items.create", title="Ship #578")
    assert tool.is_error is False
    assert tool.structured == {"title": "Ship #578", "created": True}

    mcp.initialize(_ui_initialize_params())
    listed = mcp.list_resources()
    assert any(item.get("uri") == _RESOURCE_URI for item in listed)
    negotiated = mcp.read_resource(_RESOURCE_URI)
    content = negotiated["contents"][0]
    assert content["mimeType"] == MCP_APPS_MIME_TYPE
    assert content["text"] == resource_html


def test_missing_block_raises_block_not_found(tmp_path: Path) -> None:
    _app, adapter, _cli = _build_app(tmp_path, block="missing_tool")

    with pytest.raises(BlockNotFoundError, match="missing_tool"):
        adapter.render_resource("work-items.create")


def test_empty_block_output_fails_loud(tmp_path: Path) -> None:
    _app, adapter, _cli = _build_app(tmp_path, block="empty_tool")

    with pytest.raises(ConfigurationError, match="rendered empty HTML"):
        adapter.render_resource("work-items.create")


def test_non_mapping_context_fails_loud(tmp_path: Path) -> None:
    def bad_context() -> list[str]:
        return ["heading"]

    _app, adapter, _cli = _build_app(tmp_path, context=bad_context)  # type: ignore[arg-type]

    with pytest.raises(ConfigurationError, match="must return a mapping"):
        adapter.render_resource("work-items.create")


def test_sync_and_async_context_providers(tmp_path: Path) -> None:
    calls = {"sync": 0, "async": 0}

    def sync_context() -> dict[str, str]:
        calls["sync"] += 1
        return {"heading": f"sync-{calls['sync']}"}

    async def async_context() -> dict[str, str]:
        calls["async"] += 1
        await asyncio.sleep(0)
        return {"heading": f"async-{calls['async']}"}

    _app, sync_adapter, _cli = _build_app(tmp_path, context=sync_context)
    assert "sync-1" in sync_adapter.render_resource("work-items.create")
    assert "sync-2" in sync_adapter.render_resource("work-items.create")

    templates = _write_template(tmp_path / "async")
    cli = CLI(name="async-work-items")
    group = cli.group("work-items")
    app = App(AppConfig(template_dir=templates))
    adapter = use_milo(app, cli, allowlist=("work-items.create",))

    @cli.ui_resource(_RESOURCE_URI, name="Create work item")
    def resource() -> str:
        return adapter.render_resource("work-items.create")

    @group.command("create", ui=MCPAppToolMeta(_RESOURCE_URI))
    def create(title: str) -> dict[str, str]:
        return {"title": title}

    adapter.bind(
        "work-items.create",
        template="work_items.html",
        block="create_tool",
        context=async_context,
    )
    app.freeze()

    assert "async-1" in adapter.render_resource("work-items.create")

    async def _from_running_loop() -> str:
        return adapter.render_resource("work-items.create")

    assert "async-2" in asyncio.run(_from_running_loop())
    assert calls["async"] == 2


def test_async_provider_with_running_loop_uses_per_call_worker(tmp_path: Path) -> None:
    async def async_context() -> dict[str, str]:
        await asyncio.sleep(0)
        return {"heading": "from-worker"}

    _app, adapter, _cli = _build_app(tmp_path / "loop", context=async_context)

    async def _render() -> str:
        return await asyncio.to_thread(adapter.render_resource, "work-items.create")

    html = asyncio.run(_render())
    assert "from-worker" in html

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: adapter.render_resource("work-items.create"), range(8)))
    assert all("from-worker" in item for item in results)


def test_unknown_operation_and_unfrozen_render_fail_closed(tmp_path: Path) -> None:
    templates = _write_template(tmp_path)
    cli = CLI(name="work-items")
    group = cli.group("work-items")
    app = App(AppConfig(template_dir=templates))
    adapter = use_milo(app, cli, allowlist=("work-items.create",))

    @cli.ui_resource(_RESOURCE_URI, name="Create work item")
    def resource() -> str:
        return adapter.render_resource("work-items.create")

    @group.command("create", ui=MCPAppToolMeta(_RESOURCE_URI))
    def create(title: str) -> dict[str, str]:
        return {"title": title}

    adapter.bind(
        "work-items.create",
        template="work_items.html",
        block="create_tool",
        context=lambda: {"heading": "Create a work item"},
    )

    with pytest.raises(RuntimeError, match="requires a frozen Chirp app"):
        adapter.render_resource("work-items.create")

    app.freeze()
    with pytest.raises(ConfigurationError, match="no frozen Chirp MCP App binding"):
        adapter.render_resource("work-items.missing")


def test_non_app_client_keeps_structured_tool_without_ui_resource(tmp_path: Path) -> None:
    _app, _adapter, cli = _build_app(tmp_path)
    mcp = MCPClient(cli)
    mcp.initialize({})

    tool = mcp.call("work-items.create", title="plain")
    assert tool.is_error is False
    assert tool.structured == {"title": "plain", "created": True}

    uris = {item.get("uri") for item in mcp.list_resources()}
    assert _RESOURCE_URI not in uris

    with pytest.raises(Exception, match="not negotiated"):
        mcp.read_resource(_RESOURCE_URI)


def test_render_resource_does_not_touch_request_or_private_registries() -> None:
    source = Path(__file__).resolve().parents[1] / "src" / "chirp" / "ext" / "milo.py"
    text = source.read_text(encoding="utf-8")
    assert "get_request" not in text
    assert "ContextVar" not in text
    assert "latest_result" not in text
    assert "._ui_resources" not in text
    assert "._commands" not in text
    assert "def render_resource(" in text
    assert "App.render" in text or "self._app.render" in text
