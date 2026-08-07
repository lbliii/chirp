"""Proof for #974 — freeze-time skill manifest + content digest."""

from __future__ import annotations

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from chirp import App
from chirp.skill import Skill, use_skill


def _keypair() -> tuple[Ed25519PrivateKey, bytes]:
    private = Ed25519PrivateKey.generate()
    return private, private.public_key().public_bytes_raw()


def _make_app() -> App:
    app = App()

    @app.route("/")
    def index() -> str:
        return "ok"

    return app


@pytest.mark.issue(974)
class TestSkillFreezeManifestIssue974:
    def test_digest_stable_across_freezes(self) -> None:
        private, public = _keypair()
        digests: list[str] = []

        for _ in range(2):
            skill = Skill(
                "demo",
                version="1.0.0",
                private_key=private,
                key_id="demo-1",
                public_key=public,
            )

            @skill.tool("add", description="Add two integers")
            def add(a: int, b: int) -> int:
                return a + b

            skill.add_template_source("card.html", "<div>{{ result }}</div>")
            app = _make_app()
            use_skill(app, skill)
            app.freeze()
            digests.append(skill.manifest.content_digest)

        assert digests[0] == digests[1]
        assert digests[0].startswith("sha256:")
        # assemble_manifest after freeze returns the finalized object
        assert skill.assemble_manifest() is skill.manifest

    def test_digest_changes_when_tool_schema_edits(self) -> None:
        private, public = _keypair()

        skill_a = Skill(
            "demo",
            version="1.0.0",
            private_key=private,
            key_id="demo-1",
            public_key=public,
        )

        @skill_a.tool("add", description="Add two integers")
        def add_two(a: int, b: int) -> int:
            return a + b

        skill_b = Skill(
            "demo",
            version="1.0.0",
            private_key=private,
            key_id="demo-1",
            public_key=public,
        )

        # Extra required parameter changes the MCP inputSchema shape.
        @skill_b.tool("add", description="Add two integers")
        def add_three(a: int, b: int, c: int) -> int:
            return a + b + c

        app_a, app_b = _make_app(), _make_app()
        use_skill(app_a, skill_a)
        use_skill(app_b, skill_b)
        app_a.freeze()
        app_b.freeze()

        assert skill_a.manifest.content_digest != skill_b.manifest.content_digest

    def test_digest_changes_when_template_edits(self) -> None:
        private, public = _keypair()

        def _skill_with_template(source: str) -> Skill:
            skill = Skill(
                "demo",
                version="1.0.0",
                private_key=private,
                key_id="demo-1",
                public_key=public,
            )

            @skill.tool("ping", description="Ping")
            def ping() -> str:
                return "pong"

            skill.add_template_source("card.html", source)
            return skill

        skill_a = _skill_with_template("<div>v1</div>")
        skill_b = _skill_with_template("<div>v2</div>")
        app_a, app_b = _make_app(), _make_app()
        use_skill(app_a, skill_a)
        use_skill(app_b, skill_b)
        app_a.freeze()
        app_b.freeze()

        assert skill_a.manifest.content_digest != skill_b.manifest.content_digest

    def test_manifest_immutable_after_freeze(self) -> None:
        private, public = _keypair()
        skill = Skill(
            "demo",
            version="1.0.0",
            private_key=private,
            key_id="demo-1",
            public_key=public,
        )

        @skill.tool("ping", description="Ping")
        def ping() -> str:
            return "pong"

        app = _make_app()
        use_skill(app, skill)

        with pytest.raises(RuntimeError, match="not available until"):
            _ = skill.manifest

        app.freeze()
        frozen = skill.manifest
        assert frozen.content_digest.startswith("sha256:")

        with pytest.raises(RuntimeError, match=r"after skill .* is frozen"):
            skill.add_template_source("late.html", "<p>nope</p>")
