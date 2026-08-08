"""Proof for #972 — ``skill_contract`` app.check() category."""

from __future__ import annotations

from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from chirp import App, AppConfig
from chirp.contracts.checker import check_hypermedia_surface
from chirp.contracts.rules_skill_contract import (
    SkillContractRecord,
    check_skill_contract,
)
from chirp.contracts.types import Severity
from chirp.skill import Skill, use_skill


def _app(tmp_path: Path, *, env: str = "production") -> App:
    return App(
        AppConfig(
            template_dir=str(tmp_path),
            secret_key="test-secret-key-32-bytes-long!!",
            env=env,
            skip_contract_checks=True,
        )
    )


@pytest.mark.issue(972)
class TestSkillContractIssue972:
    def test_missing_signing_key_is_error(self) -> None:
        issues = check_skill_contract(
            [
                SkillContractRecord(
                    name="demo",
                    version="1.0.0",
                    has_signing_key=False,
                    tools=(("add", ()),),
                )
            ],
            scope_registry=frozenset(),
            env="production",
        )
        assert any(
            i.category == "skill_contract"
            and i.severity == Severity.ERROR
            and "signing" in i.message
            for i in issues
        )

    def test_unknown_scope_env_aware(self) -> None:
        record = SkillContractRecord(
            name="hooks",
            version="1.0.0",
            has_signing_key=True,
            tools=(("hook", ("webhook:write",)),),
            public_key="abc",
            content_digest="sha256:" + ("a" * 64),
            manifest_complete=True,
        )
        prod = check_skill_contract(
            [record],
            scope_registry=frozenset({"other:scope"}),
            env="production",
            has_auth_middleware=True,
        )
        assert any(
            i.category == "skill_contract"
            and i.severity == Severity.ERROR
            and "webhook:write" in i.message
            for i in prod
        )
        staging = check_skill_contract(
            [record],
            scope_registry=frozenset({"other:scope"}),
            env="staging",
            has_auth_middleware=True,
        )
        assert any(i.severity == Severity.WARNING for i in staging)
        assert (
            check_skill_contract(
                [record],
                scope_registry=frozenset({"other:scope"}),
                env="development",
                has_auth_middleware=True,
            )
            == []
        )

    def test_scoped_tool_without_auth_middleware_env_aware(self) -> None:
        record = SkillContractRecord(
            name="hooks",
            version="1.0.0",
            has_signing_key=True,
            tools=(("hook", ("webhook:write",)),),
            public_key="abc",
            content_digest="sha256:" + ("a" * 64),
            manifest_complete=True,
        )
        issues = check_skill_contract(
            [record],
            scope_registry=frozenset({"webhook:write"}),
            env="production",
            has_auth_middleware=False,
        )
        assert any(
            i.category == "skill_contract"
            and i.severity == Severity.ERROR
            and "AuthMiddleware" in i.message
            for i in issues
        )

    def test_incomplete_manifest_is_error(self) -> None:
        issues = check_skill_contract(
            [
                SkillContractRecord(
                    name="broken",
                    version="1.0.0",
                    has_signing_key=True,
                    tools=(("add", ()),),
                    public_key="",
                    content_digest="",
                    manifest_complete=False,
                )
            ],
            scope_registry=frozenset(),
            env="development",
        )
        assert any(
            i.category == "skill_contract"
            and i.severity == Severity.ERROR
            and "incomplete" in i.message
            for i in issues
        )

    def test_use_skill_registers_check_and_flags_missing_key(self, tmp_path: Path) -> None:
        app = _app(tmp_path, env="production")
        skill = Skill("demo", version="1.0.0", private_key=None, key_id="demo-1")

        @skill.tool("add", description="Add")
        def add(a: int, b: int) -> int:
            return a + b

        use_skill(app, skill)
        app.freeze()
        result = check_hypermedia_surface(app)
        skill_issues = [i for i in result.issues if i.category == "skill_contract"]
        assert skill_issues
        assert any("signing" in i.message for i in skill_issues)

    def test_healthy_skill_silent(self, tmp_path: Path) -> None:
        app = _app(tmp_path, env="production")
        private = Ed25519PrivateKey.generate()
        skill = Skill("demo", version="1.0.0", private_key=private, key_id="demo-1")

        @skill.tool("add", description="Add")
        def add(a: int, b: int) -> int:
            return a + b

        use_skill(app, skill)
        app.freeze()
        result = check_hypermedia_surface(app)
        assert [i for i in result.issues if i.category == "skill_contract"] == []
