"""Proof for #981 — SkillRegistry + mount_skills + discovery + aggregated /mcp."""

from __future__ import annotations

import json
from typing import Any

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from chirp import App
from chirp.skill import (
    DEFAULT_DISCOVERY_PATH,
    Skill,
    SkillRegistry,
    mount_skills,
)
from chirp.testing import TestClient

_META_PROTOCOL_VERSION = "io.modelcontextprotocol/protocolVersion"


def _keypair() -> tuple[Ed25519PrivateKey, bytes]:
    private = Ed25519PrivateKey.generate()
    return private, private.public_key().public_bytes_raw()


def _make_skill(
    name: str,
    tool_name: str,
    *,
    version: str = "1.0.0",
    description: str = "",
) -> Skill:
    private, public = _keypair()
    skill = Skill(
        name,
        version=version,
        private_key=private,
        key_id=f"{name}-key",
        public_key=public,
    )

    @skill.tool(tool_name, description=description or f"{name}.{tool_name}")
    def handler(value: str) -> dict[str, str]:
        return {"skill": name, "tool": tool_name, "value": value}

    return skill


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


@pytest.mark.issue(981)
class TestSkillRegistryIssue981:
    def test_registry_stores_skills_by_name(self) -> None:
        registry = SkillRegistry()
        alpha = _make_skill("alpha", "echo_alpha")
        beta = _make_skill("beta", "echo_beta")
        registry.add(alpha)
        registry.add(beta)

        assert len(registry) == 2
        assert "alpha" in registry
        assert registry.get("alpha") is alpha
        assert registry.get("missing") is None
        assert registry.names == frozenset({"alpha", "beta"})
        assert registry.skills() == (alpha, beta)

        with pytest.raises(ValueError, match="already registered"):
            registry.add(_make_skill("alpha", "other"))

    def test_mount_skills_from_registry_and_discovery_lists_manifests(self) -> None:
        alpha = _make_skill("alpha", "echo_alpha", version="1.2.0")
        beta = _make_skill("beta", "echo_beta", version="0.3.1")
        registry = SkillRegistry()
        registry.add(alpha)
        registry.add(beta)

        app = App()

        @app.route("/")
        def index() -> str:
            return "ok"

        mounted = mount_skills(app, registry)
        assert mounted is registry
        assert registry.mounted is True
        assert registry.discovery_path == DEFAULT_DISCOVERY_PATH

        app.freeze()
        manifests = registry.manifests()
        assert len(manifests) == 2
        assert manifests[0].name == "alpha"
        assert manifests[0].version == "1.2.0"
        assert manifests[0].tools == ("echo_alpha",)
        assert manifests[0].content_digest.startswith("sha256:")
        assert manifests[1].name == "beta"
        assert manifests[1].tools == ("echo_beta",)

        import asyncio

        async def _probe() -> None:
            async with TestClient(app) as client:
                response = await client.get("/skills")
                assert response.status == 200
                assert "application/json" in response.content_type
                body = json.loads(response.text)
                assert set(body.keys()) == {"skills"}
                by_name = {entry["name"]: entry for entry in body["skills"]}
                assert by_name["alpha"]["version"] == "1.2.0"
                assert by_name["alpha"]["tools"] == ["echo_alpha"]
                assert by_name["beta"]["tools"] == ["echo_beta"]
                assert by_name["alpha"]["content_digest"] == manifests[0].content_digest
                assert by_name["beta"]["content_digest"] == manifests[1].content_digest

        asyncio.run(_probe())

        with pytest.raises(RuntimeError, match="already mounted"):
            mount_skills(app, registry)

        with pytest.raises(RuntimeError, match="Cannot add skills after"):
            registry.add(_make_skill("gamma", "echo_gamma"))

    def test_aggregated_mcp_serves_tools_from_mounted_skills(self) -> None:
        alpha = _make_skill("alpha", "echo_alpha")
        beta = _make_skill("beta", "echo_beta")

        app = App()

        @app.route("/")
        def index() -> str:
            return "ok"

        mount_skills(app, (alpha, beta))

        import asyncio

        async def _probe() -> None:
            async with TestClient(app) as client:
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
                listed_body = json.loads(listed.text)
                tool_names = {t["name"] for t in listed_body["result"]["tools"]}
                assert tool_names == {"echo_alpha", "echo_beta"}

                called = await client.post(
                    "/mcp",
                    json={
                        "jsonrpc": "2.0",
                        "method": "tools/call",
                        "id": 2,
                        "params": _modern_mcp_params(
                            name="echo_beta",
                            arguments={"value": "hi"},
                        ),
                    },
                    headers=_modern_mcp_headers("tools/call", "echo_beta"),
                )
                assert called.status == 200
                called_body = json.loads(called.text)
                text = called_body["result"]["content"][0]["text"]
                # MCP _format_result stringifies Envelope (repr); prove dispatch.
                assert "echo_beta" in text
                assert "'value': 'hi'" in text or '"value": "hi"' in text
                assert "skill='beta'" in text or "'skill': 'beta'" in text

                # Direct registry path still returns a signed Envelope.
                envelope = await app.tools.call_tool("echo_alpha", {"value": "x"})
                from chirp.skill import Envelope, verify_envelope

                assert isinstance(envelope, Envelope)
                assert envelope.payload == {
                    "skill": "alpha",
                    "tool": "echo_alpha",
                    "value": "x",
                }
                assert verify_envelope(envelope, alpha.public_key) is True

        asyncio.run(_probe())

    def test_duplicate_tool_names_across_skills_fail_loud(self) -> None:
        left = _make_skill("left", "shared")
        right = _make_skill("right", "shared")
        app = App()

        @app.route("/")
        def index() -> str:
            return "ok"

        with pytest.raises(ValueError, match="Duplicate tool name"):
            mount_skills(app, (left, right))

    def test_custom_discovery_path(self) -> None:
        skill = _make_skill("solo", "ping")
        app = App()

        @app.route("/")
        def index() -> str:
            return "ok"

        registry = mount_skills(app, (skill,), discovery_path="/.well-known/skills")
        assert registry.discovery_path == "/.well-known/skills"
        app.freeze()

        import asyncio

        async def _probe() -> None:
            async with TestClient(app) as client:
                response = await client.get("/.well-known/skills")
                assert response.status == 200
                body = json.loads(response.text)
                assert body["skills"][0]["name"] == "solo"
                assert body["skills"][0]["tools"] == ["ping"]

        asyncio.run(_probe())
