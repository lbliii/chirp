"""Proof for #970 — use_skill mounts tools; skill.tool wraps Envelope; Manifest round-trip."""

from __future__ import annotations

import json

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from chirp import App
from chirp.skill import (
    Envelope,
    Manifest,
    Skill,
    assemble_manifest,
    use_skill,
    verify_envelope,
)


def _keypair() -> tuple[Ed25519PrivateKey, bytes]:
    private = Ed25519PrivateKey.generate()
    return private, private.public_key().public_bytes_raw()


@pytest.mark.issue(970)
class TestSkillPackageIssue970:
    def test_use_skill_mounts_tools_and_tool_returns_envelope(self) -> None:
        private, public = _keypair()
        skill = Skill(
            "demo",
            version="1.0.0",
            private_key=private,
            key_id="demo-key-1",
            public_key=public,
        )

        @skill.tool("add", description="Add two integers")
        def add(a: int, b: int) -> int:
            return a + b

        app = App()

        @app.route("/")
        def index() -> str:
            return "ok"

        use_skill(app, skill)
        assert len(app._pending_tools) == 1
        assert app._pending_tools[0].name == "add"

        app._ensure_frozen()
        assert "add" in app.tools

        import asyncio

        result = asyncio.run(app.tools.call_tool("add", {"a": 2, "b": 3}))
        assert isinstance(result, Envelope)
        assert result.payload == 5
        assert result.skill == "demo"
        assert result.version == "1.0.0"
        assert result.tool == "add"
        assert result.key_id == "demo-key-1"
        assert verify_envelope(result, public) is True

    def test_manifest_serializes_round_trip(self) -> None:
        private, public = _keypair()
        skill = Skill(
            "weather",
            version="0.2.1",
            private_key=private,
            key_id="wx-1",
            public_key=public,
            provider_keys=("OPENWEATHER_API_KEY",),
        )

        @skill.tool("forecast", description="Get a forecast")
        def forecast(city: str) -> dict[str, str]:
            return {"city": city, "summary": "clear"}

        manifest = skill.assemble_manifest()
        assert isinstance(manifest, Manifest)
        assert manifest.name == "weather"
        assert manifest.version == "0.2.1"
        assert manifest.tools == ("forecast",)
        assert manifest.provider_keys == ("OPENWEATHER_API_KEY",)
        assert manifest.content_digest.startswith("sha256:")
        assert manifest.public_key  # non-empty encoded key

        wire = manifest.to_dict()
        # JSON round-trip exercises serializability.
        restored = Manifest.from_dict(json.loads(json.dumps(wire)))
        assert restored == manifest

        # assemble_manifest helper agrees with Skill.assemble_manifest.
        assert (
            assemble_manifest(
                name="weather",
                version="0.2.1",
                tools=("forecast",),
                public_key=public,
                provider_keys=("OPENWEATHER_API_KEY",),
            )
            == manifest
        )
