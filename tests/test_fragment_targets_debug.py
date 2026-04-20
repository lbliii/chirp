"""Tests for the /__chirp/debug/fragment-targets endpoint."""

import json

import pytest

from chirp import App
from chirp.config import AppConfig
from chirp.templating.fragment_target_registry import (
    PageShellContract,
    PageShellTarget,
)
from chirp.testing import TestClient

_PATH = "/__chirp/debug/fragment-targets"


def _app(*, debug: bool, tmp_path) -> App:
    return App(AppConfig(template_dir=str(tmp_path), debug=debug))


@pytest.mark.asyncio
async def test_endpoint_404_when_debug_false(tmp_path):
    app = _app(debug=False, tmp_path=tmp_path)
    async with TestClient(app) as client:
        response = await client.get(_PATH)
    assert response.status == 404


@pytest.mark.asyncio
async def test_endpoint_200_when_debug_true_empty_registry(tmp_path):
    app = _app(debug=True, tmp_path=tmp_path)
    async with TestClient(app) as client:
        response = await client.get(_PATH)
    assert response.status == 200
    payload = json.loads(response.body)
    assert payload == {"contracts": [], "unscoped": []}


@pytest.mark.asyncio
async def test_endpoint_reports_contract_targets(tmp_path):
    app = _app(debug=True, tmp_path=tmp_path)
    contract = PageShellContract(
        name="myshell",
        description="Test shell",
        targets=(
            PageShellTarget(
                target_id="main",
                fragment_block="page_root",
                triggers_shell_update=False,
                required=True,
                omit_outer_layouts=True,
            ),
            PageShellTarget(
                target_id="page-root",
                fragment_block="page_root_inner",
                triggers_shell_update=True,
                required=True,
            ),
        ),
    )
    app._mutable_state.fragment_target_registry.register_contract(contract)

    async with TestClient(app) as client:
        response = await client.get(_PATH)
    payload = json.loads(response.body)

    assert len(payload["contracts"]) == 1
    entry = payload["contracts"][0]
    assert entry["name"] == "myshell"
    assert entry["description"] == "Test shell"
    assert len(entry["targets"]) == 2
    by_id = {t["target_id"]: t for t in entry["targets"]}
    assert by_id["main"]["fragment_block"] == "page_root"
    assert by_id["main"]["triggers_shell_update"] is False
    assert by_id["main"]["required"] is True
    assert by_id["main"]["omit_outer_layouts"] is True
    assert by_id["page-root"]["fragment_block"] == "page_root_inner"
    assert by_id["page-root"]["triggers_shell_update"] is True
    assert payload["unscoped"] == []


@pytest.mark.asyncio
async def test_endpoint_reports_unscoped_targets(tmp_path):
    app = _app(debug=True, tmp_path=tmp_path)
    app._mutable_state.fragment_target_registry.register(
        "standalone", fragment_block="standalone_block"
    )

    async with TestClient(app) as client:
        response = await client.get(_PATH)
    payload = json.loads(response.body)

    assert payload["contracts"] == []
    assert len(payload["unscoped"]) == 1
    assert payload["unscoped"][0]["target_id"] == "standalone"
    assert payload["unscoped"][0]["fragment_block"] == "standalone_block"
