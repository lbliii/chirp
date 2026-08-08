"""Proof for #984 — EnvKeystore + key-status presence report + leak guard."""

from __future__ import annotations

import json
from typing import Any

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from chirp import App
from chirp.skill import (
    KEY_STATUS_TOOL,
    EnvKeystore,
    KeyStatus,
    SecretLeakError,
    Skill,
    assert_no_secret_leak,
    mount_skills,
    register_key_status_tool,
)
from chirp.testing import TestClient

_META_PROTOCOL_VERSION = "io.modelcontextprotocol/protocolVersion"
_SECRET = "sk-live-do-not-leak-984-super-secret"


def _keypair() -> tuple[Ed25519PrivateKey, bytes]:
    private = Ed25519PrivateKey.generate()
    return private, private.public_key().public_bytes_raw()


def _make_skill(
    name: str,
    tool_name: str,
    *,
    provider_keys: tuple[str, ...] = (),
) -> Skill:
    private, public = _keypair()
    skill = Skill(
        name,
        version="1.0.0",
        private_key=private,
        key_id=f"{name}-key",
        public_key=public,
        provider_keys=provider_keys,
    )

    @skill.tool(tool_name, description=f"{name}.{tool_name}")
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


@pytest.mark.issue(984)
class TestEnvKeystoreIssue984:
    def test_resolve_by_name_from_env(self) -> None:
        store = EnvKeystore(
            {
                "OPENWEATHER_API_KEY": _SECRET,
                "EMPTY_KEY": "",
            }
        )
        assert store.present("OPENWEATHER_API_KEY") is True
        assert store.get("OPENWEATHER_API_KEY") == _SECRET
        assert store.resolve("OPENWEATHER_API_KEY") == _SECRET
        assert store.present("EMPTY_KEY") is False
        assert store.get("EMPTY_KEY") is None
        assert store.present("MISSING_KEY") is False
        with pytest.raises(KeyError, match="MISSING_KEY"):
            store.resolve("MISSING_KEY")
        # Repr never dumps secrets.
        assert _SECRET not in repr(store)
        assert "custom" in repr(store)

    def test_status_reports_presence_without_values(self) -> None:
        store = EnvKeystore(
            {
                "OPENWEATHER_API_KEY": _SECRET,
                "OTHER_KEY": "also-secret",
            }
        )
        statuses = store.status(("OPENWEATHER_API_KEY", "MISSING_KEY", "OPENWEATHER_API_KEY"))
        assert statuses == (
            KeyStatus(name="OPENWEATHER_API_KEY", present=True),
            KeyStatus(name="MISSING_KEY", present=False),
        )
        document = store.status_document(("OPENWEATHER_API_KEY", "MISSING_KEY"))
        assert document == {
            "keys": [
                {"name": "OPENWEATHER_API_KEY", "present": True},
                {"name": "MISSING_KEY", "present": False},
            ]
        }
        blob = json.dumps(document)
        assert _SECRET not in blob
        assert "also-secret" not in blob
        assert "value" not in blob

    def test_leak_guard_rejects_secret_in_payload(self) -> None:
        assert_no_secret_leak({"keys": [{"name": "K", "present": True}]}, secrets=(_SECRET,))
        with pytest.raises(SecretLeakError, match="leak"):
            assert_no_secret_leak(
                {"keys": [{"name": "K", "present": True, "value": _SECRET}]},
                secrets=(_SECRET,),
            )

    def test_key_status_tool_reports_presence_no_secret_leak(self) -> None:
        weather = _make_skill(
            "weather",
            "forecast",
            provider_keys=("OPENWEATHER_API_KEY", "GEOCODE_API_KEY"),
        )
        maps = _make_skill(
            "maps",
            "geocode",
            provider_keys=("GEOCODE_API_KEY",),  # shared name — deduped
        )
        keystore = EnvKeystore(
            {
                "OPENWEATHER_API_KEY": _SECRET,
                # GEOCODE_API_KEY intentionally unset
            }
        )

        app = App()

        @app.route("/")
        def index() -> str:
            return "ok"

        registry = mount_skills(app, (weather, maps), keystore=keystore)
        assert registry.provider_key_names() == (
            "OPENWEATHER_API_KEY",
            "GEOCODE_API_KEY",
        )

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
                assert KEY_STATUS_TOOL in tool_names
                assert "forecast" in tool_names
                assert "geocode" in tool_names

                called = await client.post(
                    "/mcp",
                    json={
                        "jsonrpc": "2.0",
                        "method": "tools/call",
                        "id": 2,
                        "params": _modern_mcp_params(name=KEY_STATUS_TOOL, arguments={}),
                    },
                    headers=_modern_mcp_headers("tools/call", KEY_STATUS_TOOL),
                )
                assert called.status == 200
                called_body = json.loads(called.text)
                text = called_body["result"]["content"][0]["text"]
                # MCP may stringify the dict; prove presence semantics + no leak.
                assert "OPENWEATHER_API_KEY" in text
                assert "GEOCODE_API_KEY" in text
                assert "True" in text or "true" in text
                assert "False" in text or "false" in text
                assert _SECRET not in text
                assert _SECRET not in called.text
                assert "'value'" not in text
                assert '"value"' not in text

                # Direct registry path: structured document, no secrets.
                result = await app.tools.call_tool(KEY_STATUS_TOOL, {})
                assert result == {
                    "keys": [
                        {"name": "OPENWEATHER_API_KEY", "present": True},
                        {"name": "GEOCODE_API_KEY", "present": False},
                    ]
                }
                assert _SECRET not in json.dumps(result)

        asyncio.run(_probe())

    def test_register_key_status_tool_standalone(self) -> None:
        app = App()

        @app.route("/")
        def index() -> str:
            return "ok"

        store = EnvKeystore({"ALPHA": _SECRET})
        name = register_key_status_tool(app, store, names=("ALPHA", "BETA"))
        assert name == KEY_STATUS_TOOL
        app.freeze()

        import asyncio

        async def _probe() -> None:
            result = await app.tools.call_tool(KEY_STATUS_TOOL, {})
            assert result == {
                "keys": [
                    {"name": "ALPHA", "present": True},
                    {"name": "BETA", "present": False},
                ]
            }
            assert _SECRET not in json.dumps(result)

        asyncio.run(_probe())

    def test_key_status_tool_name_collision_fails_loud(self) -> None:
        colliding = _make_skill("bad", KEY_STATUS_TOOL, provider_keys=("K",))
        app = App()

        @app.route("/")
        def index() -> str:
            return "ok"

        with pytest.raises(ValueError, match="reserved for the host EnvKeystore"):
            mount_skills(app, (colliding,), keystore=EnvKeystore({}))
