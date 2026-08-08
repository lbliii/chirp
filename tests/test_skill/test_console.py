"""Proof for #982 — hypermedia console browse + detail + reliability score."""

from __future__ import annotations

import asyncio

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from chirp import App
from chirp.skill import (
    DEFAULT_CONSOLE_PATH,
    Skill,
    SkillRegistry,
    mount_console,
    mount_skills,
)
from chirp.skill.console import ReliabilityScore, ReliabilityStore
from chirp.skill.smoke import (
    FIXTURE_CORPUS,
    make_fixture_skill,
    run_smoke,
)
from chirp.testing import TestClient


def _keypair() -> tuple[Ed25519PrivateKey, bytes]:
    private = Ed25519PrivateKey.generate()
    return private, private.public_key().public_bytes_raw()


def _make_skill(
    name: str,
    tool_name: str,
    *,
    version: str = "1.0.0",
    provider_keys: tuple[str, ...] = (),
) -> Skill:
    private, public = _keypair()
    skill = Skill(
        name,
        version=version,
        private_key=private,
        key_id=f"{name}-key",
        public_key=public,
        provider_keys=provider_keys,
    )

    @skill.tool(tool_name, description=f"{name}.{tool_name}")
    def handler(value: str) -> dict[str, str]:
        return {"skill": name, "tool": tool_name, "value": value}

    return skill


@pytest.mark.issue(982)
class TestSkillConsoleIssue982:
    def test_reliability_score_from_smoke(self) -> None:
        skill = make_fixture_skill()
        app = App()

        @app.route("/")
        def index() -> str:
            return "ok"

        mount_skills(app, (skill,))
        app.freeze()
        report = run_smoke(app, FIXTURE_CORPUS)
        score = ReliabilityScore.from_smoke(report)
        assert score.status == "pass"
        assert score.total == len(FIXTURE_CORPUS)
        assert score.passed == score.total
        assert score.ratio == 1.0
        assert "pass" in score.label

        unknown = ReliabilityScore.unknown()
        assert unknown.status == "unknown"
        assert unknown.ratio is None

    def test_console_list_and_detail_render_manifest_and_score(self) -> None:
        alpha = _make_skill(
            "alpha", "echo_alpha", version="1.2.0", provider_keys=("OPENAI_API_KEY",)
        )
        beta = _make_skill("beta", "echo_beta", version="0.3.1")
        registry = SkillRegistry()
        registry.add(alpha)
        registry.add(beta)

        app = App()
        mount_skills(app, registry)

        scores = ReliabilityStore()
        scores.record(
            "alpha",
            ReliabilityScore(passed=2, total=2, status="pass"),
        )
        scores.record(
            "beta",
            ReliabilityScore(passed=0, total=1, status="fail"),
        )

        def key_status(skill_name: str, names: tuple[str, ...]) -> dict[str, bool | None]:
            assert skill_name == "alpha"
            return {names[0]: True}

        path = mount_console(
            app,
            registry,
            scores=scores,
            key_status=key_status,
        )
        assert path == DEFAULT_CONSOLE_PATH
        app.freeze()

        async def _probe() -> None:
            async with TestClient(app) as client:
                listed = await client.get("/console")
                assert listed.status == 200
                assert "text/html" in listed.content_type
                body = listed.text
                assert "Skill console" in body
                assert "alpha" in body
                assert "beta" in body
                assert "1.2.0" in body
                assert "2/2 pass" in body
                assert "0/1 fail" in body
                assert 'id="skill_list"' in body

                detail = await client.get("/console/alpha")
                assert detail.status == 200
                text = detail.text
                assert 'id="skill_detail"' in text
                assert "alpha" in text
                assert "1.2.0" in text
                assert "echo_alpha" in text
                assert "sha256:" in text
                assert "Reliability" in text
                assert "2/2 pass" in text
                assert "Contract" in text
                assert "OPENAI_API_KEY" in text
                assert "present" in text
                assert 'id="skill_console_live_log"' in text
                assert 'data-chirp-skill-console="live-log"' in text

                missing = await client.get("/console/missing")
                assert missing.status == 404

                # htmx fragment negotiation for the list Page block
                frag = await client.get(
                    "/console",
                    headers={"HX-Request": "true"},
                )
                assert frag.status == 200
                assert "Skill console" in frag.text
                assert "<html" not in frag.text.lower()

        asyncio.run(_probe())

    def test_keys_unknown_without_keystore_hook(self) -> None:
        skill = _make_skill("keyed", "echo_keyed", provider_keys=("ANTHROPIC_API_KEY",))
        registry = SkillRegistry()
        registry.add(skill)
        app = App()
        mount_skills(app, registry)
        mount_console(app, registry)
        app.freeze()

        async def _probe() -> None:
            async with TestClient(app) as client:
                detail = await client.get("/console/keyed")
                assert detail.status == 200
                assert "ANTHROPIC_API_KEY" in detail.text
                assert "unknown" in detail.text
                assert "Keystore not wired" in detail.text

        asyncio.run(_probe())

    def test_mount_console_rejects_non_registry(self) -> None:
        app = App()
        with pytest.raises(TypeError, match="SkillRegistry"):
            mount_console(app, [])  # type: ignore[arg-type]
