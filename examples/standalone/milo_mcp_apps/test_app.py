"""Executable proof for the Milo MCP Apps registration preview."""

import pytest

from chirp.testing import TestClient
from examples.standalone.milo_mcp_apps.app import RESOURCE_URI, adapter, app, cli

pytestmark = pytest.mark.issue(577)


def test_binding_freezes_without_mutating_the_milo_cli() -> None:
    commands_before = list(cli.walk_commands())
    resources_before = cli.walk_ui_resources()

    app.freeze()

    binding = adapter.bindings[0]
    assert binding.operation_id == "work-items.create"
    assert binding.resource_uri == RESOURCE_URI
    assert binding.template == "work_items.html"
    assert binding.block == "create_tool"
    assert list(cli.walk_commands()) == commands_before
    assert cli.walk_ui_resources() == resources_before


async def test_ordinary_chirp_page_still_uses_the_shared_template() -> None:
    async with TestClient(app) as client:
        response = await client.get("/")

    assert response.status == 200
    assert "Milo MCP Apps registration preview" in response.text
    assert "rendering is pending #578" in response.text
