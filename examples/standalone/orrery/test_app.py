"""Proof for #985 — Orrery Railway dogfood host (N skills + /mcp + console)."""

from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest

from chirp.skill.publish import run_publish_gate
from chirp.testing import TestClient

_META_PROTOCOL_VERSION = "io.modelcontextprotocol/protocolVersion"
N_DOGFOOD_SKILLS = 10


def _modern_mcp_params(**extra: Any) -> dict[str, Any]:
    params: dict[str, Any] = {
        "_meta": {
            _META_PROTOCOL_VERSION: "2026-07-28",
            "io.modelcontextprotocol/clientCapabilities": {},
        },
    }
    params.update(extra)
    return params


def _modern_mcp_headers(method: str, name: str | None = None) -> dict[str, str]:
    headers = {
        "content-type": "application/json",
        "mcp-protocol-version": "2026-07-28",
        "mcp-method": method,
    }
    if name is not None:
        headers["mcp-name"] = name
    return headers


@pytest.mark.issue(985)
class TestOrreryDogfoodIssue985:
    async def test_host_mounts_n_skills_and_surfaces(self, example_app) -> None:
        assert N_DOGFOOD_SKILLS == 10
        async with TestClient(example_app) as client:
            home = await client.get("/")
            assert home.status == 200
            assert "Orrery" in home.text
            assert "gaze" in home.text
            assert "resolve" in home.text
            assert "star" in home.text
            # Branded page uses inline <style> + Google Fonts; default secure_stack
            # CSP blanked production until style-src/font-src were relaxed.
            csp = dict(home.headers).get("content-security-policy", "")
            assert "style-src" in csp
            assert "'unsafe-inline'" in csp
            assert "fonts.googleapis.com" in csp
            assert "fonts.gstatic.com" in csp

            discovery = await client.get("/skills")
            assert discovery.status == 200
            body = json.loads(discovery.text)
            names = {entry["name"] for entry in body["skills"]}
            assert names == {
                "gaze",
                "resolve",
                "star",
                "mcp-verify",
                "release-readiness",
                "production-receipt",
                "artifact-qa",
                "research-evidence",
                "handoff-receipt",
                "reliability-status",
            }

            console = await client.get("/console")
            assert console.status == 200
            assert "gaze" in console.text

            detail = await client.get("/console/gaze")
            assert detail.status == 200
            assert "look_at" in detail.text

            trust_detail = await client.get("/console/mcp-verify")
            assert trust_detail.status == 200
            assert "verify_mcp" in trust_detail.text

    async def test_aggregated_mcp_lists_and_invokes_dogfood_tools(self, example_app) -> None:
        async with TestClient(example_app) as client:
            listed = await client.post(
                "/mcp",
                json={
                    "jsonrpc": "2.0",
                    "method": "tools/list",
                    "id": 1,
                    "params": _modern_mcp_params(),
                },
                headers=_modern_mcp_headers("tools/list"),
            )
            assert listed.status == 200
            tool_names = {t["name"] for t in json.loads(listed.text)["result"]["tools"]}
            assert tool_names == {
                "look_at",
                "resolve_name",
                "seal_label",
                "verify_mcp",
                "release_readiness",
                "production_receipt",
                "artifact_qa",
                "research_evidence",
                "handoff_receipt",
                "reliability_status",
            }

            called = await client.post(
                "/mcp",
                json={
                    "jsonrpc": "2.0",
                    "method": "tools/call",
                    "id": 2,
                    "params": _modern_mcp_params(
                        name="look_at",
                        arguments={"target": "Vega"},
                    ),
                },
                headers=_modern_mcp_headers("tools/call", "look_at"),
            )
            assert called.status == 200
            text = json.loads(called.text)["result"]["content"][0]["text"]
            assert "Vega" in text
            assert "look_at" in text or "gaze" in text

            verified = await client.post(
                "/mcp",
                json={
                    "jsonrpc": "2.0",
                    "method": "tools/call",
                    "id": 3,
                    "params": _modern_mcp_params(
                        name="verify_mcp",
                        arguments={"endpoint": "https://orrery.example/mcp"},
                    ),
                },
                headers=_modern_mcp_headers("tools/call", "verify_mcp"),
            )
            assert verified.status == 200
            verified_text = json.loads(verified.text)["result"]["content"][0]["text"]
            assert "https://orrery.example/mcp" in verified_text
            assert "compatible-demo" in verified_text

    async def test_agent_invocation_streams_on_home_feed(self, example_app) -> None:
        async with TestClient(example_app) as client:

            async def call_after_delay() -> None:
                await asyncio.sleep(0.1)
                await client.post(
                    "/mcp",
                    json={
                        "jsonrpc": "2.0",
                        "method": "tools/call",
                        "id": 4,
                        "params": _modern_mcp_params(
                            name="seal_label",
                            arguments={"label": "Orion"},
                        ),
                    },
                    headers=_modern_mcp_headers("tools/call", "seal_label"),
                )
                await asyncio.sleep(0.15)

            task = asyncio.create_task(call_after_delay())
            result = await client.sse("/feed", max_events=1, timeout=2.0)
            await task

            assert result.status == 200
            assert result.events
            event = result.events[0]
            assert (event.event or "message") == "message"
            assert "seal_label" in event.data
            assert "Orion" in event.data

    def test_dogfood_skills_pass_publish_oracle(self, example_app) -> None:
        from dogfood import DOGFOOD_CORPUS

        receipt = run_publish_gate(example_app, DOGFOOD_CORPUS)
        assert receipt.passed, receipt.to_dict()
        assert receipt.smoke is not None
        assert receipt.smoke.passed
