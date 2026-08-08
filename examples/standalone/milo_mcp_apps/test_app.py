"""Executable proof for Milo MCP Apps named-block resource rendering (#578)."""

from __future__ import annotations

import pytest
from milo.mcp_apps import MCP_APPS_EXTENSION_ID, MCP_APPS_MIME_TYPE
from milo.testing import MCPClient

from chirp.testing import TestClient
from examples.standalone.milo_mcp_apps.app import RESOURCE_URI, adapter, app, cli

pytestmark = pytest.mark.issue(578)


def test_binding_and_resource_render_share_the_named_block() -> None:
    app.freeze()
    binding = adapter.bindings[0]
    assert binding.operation_id == "work-items.create"
    assert binding.resource_uri == RESOURCE_URI
    assert binding.template == "work_items.html"
    assert binding.block == "create_tool"

    html = adapter.render_resource("work-items.create")
    assert 'id="create-title"' in html
    assert "Create a work item" in html


async def test_browser_htmx_tool_and_resource_derive_from_one_template() -> None:
    app.freeze()

    async with TestClient(app) as client:
        full = await client.get("/")
        page = await client.get("/create-tool")
        fragment = await client.fragment("/create-tool/fragment")

    assert full.status == 200
    assert "Milo MCP Apps named-block resource" in full.text
    assert 'id="create-title"' in page.text
    assert fragment.text == adapter.render_resource("work-items.create")

    mcp = MCPClient(cli)
    tool = mcp.call("work-items.create", title="from-example")
    assert tool.is_error is False
    assert tool.structured == {"title": "from-example", "created": True}

    mcp.initialize(
        {
            "capabilities": {
                "extensions": {
                    MCP_APPS_EXTENSION_ID: {"mimeTypes": [MCP_APPS_MIME_TYPE]},
                }
            }
        }
    )
    content = mcp.read_resource(RESOURCE_URI)["contents"][0]
    assert content["mimeType"] == MCP_APPS_MIME_TYPE
    assert content["text"] == fragment.text
