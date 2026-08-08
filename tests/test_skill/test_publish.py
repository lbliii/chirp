"""Proof for #976 — skill publish gate (check + freeze + smoke) + receipt."""

from __future__ import annotations

import json
import sys
import types

import pytest

from chirp import App
from chirp.skill import Skill, use_skill
from chirp.skill.publish import (
    STAGE_CHECK,
    STAGE_FREEZE,
    STAGE_SMOKE,
    format_publish_receipt,
    run_publish_gate,
)
from chirp.skill.smoke import (
    FAILURE_REFUSAL,
    FIXTURE_CORPUS,
    CorpusPrompt,
    make_fixture_skill,
)


def _make_app() -> App:
    app = App()

    @app.route("/")
    def index() -> str:
        return "ok"

    return app


def _register_app(monkeypatch: pytest.MonkeyPatch, name: str, app: App) -> str:
    mod = types.ModuleType(name)
    mod.app = app  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, name, mod)
    return f"{name}:app"


@pytest.mark.issue(976)
class TestSkillPublishGateIssue976:
    def test_fixture_skill_passes_all_three_stages(self) -> None:
        app = _make_app()
        use_skill(app, make_fixture_skill())

        receipt = run_publish_gate(app, FIXTURE_CORPUS)
        assert [s.name for s in receipt.stages] == [
            STAGE_CHECK,
            STAGE_FREEZE,
            STAGE_SMOKE,
        ]
        assert receipt.passed
        assert all(s.passed for s in receipt.stages)
        assert receipt.manifests
        assert receipt.manifests[0]["content_digest"].startswith("sha256:")
        assert receipt.smoke is not None
        assert receipt.smoke.passed

        text = format_publish_receipt(receipt)
        assert "[PASS] check" in text
        assert "[PASS] freeze" in text
        assert "[PASS] smoke" in text
        assert "publish gate passed" in text

    def test_injected_check_failure_blocks_with_full_receipt(self) -> None:
        """Unsigned skill → skill_contract ERROR; all stages still run."""
        app = _make_app()
        skill = Skill("unsigned", version="0.1.0", key_id="u1")

        @skill.tool("echo", description="Echo")
        def echo(message: str) -> dict[str, str]:
            return {"message": message}

        use_skill(app, skill)

        receipt = run_publish_gate(app, FIXTURE_CORPUS[:1])
        assert not receipt.passed
        assert [s.name for s in receipt.stages] == [
            STAGE_CHECK,
            STAGE_FREEZE,
            STAGE_SMOKE,
        ]
        check = receipt.stages[0]
        assert not check.passed
        assert check.detail is not None
        assert "skill_contract" in check.detail["categories"]
        # Freeze still reports (empty digest / public key).
        assert not receipt.stages[1].passed
        text = format_publish_receipt(receipt)
        assert "[FAIL] check" in text
        assert "publish blocked" in text
        payload = receipt.to_dict()
        assert payload["ok"] is False
        assert len(payload["stages"]) == 3

    def test_injected_smoke_failure_blocks_with_receipt(self) -> None:
        app = _make_app()
        use_skill(app, make_fixture_skill())

        def refuse(prompt: CorpusPrompt, _engine: object) -> str:
            return f"I don't have data on that regarding {prompt.tool}."

        receipt = run_publish_gate(app, FIXTURE_CORPUS[:1], answer_fn=refuse)
        assert not receipt.passed
        assert receipt.stages[0].passed  # check
        assert receipt.stages[1].passed  # freeze
        smoke = receipt.stages[2]
        assert not smoke.passed
        assert receipt.smoke is not None
        assert not receipt.smoke.passed
        assert receipt.smoke.failures[0].verdict.failure_class == FAILURE_REFUSAL
        text = format_publish_receipt(receipt)
        assert "publish blocked" in text
        assert "smoke" in text


@pytest.mark.issue(976)
def test_cli_skill_publish_fixture_pass_and_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from chirp.cli._skill_publish import collect_skill_publish_result

    app = _make_app()
    use_skill(app, make_fixture_skill())
    app_import = _register_app(monkeypatch, "_chirp_976_publish_app", app)

    result = collect_skill_publish_result(app_import, fixture=True, json_output=True)
    assert result.exit_code == 0
    assert result["ok"] is True
    assert result["stages"][0]["name"] == "check"
    assert result["stages"][1]["name"] == "freeze"
    assert result["stages"][2]["name"] == "smoke"
    parsed = json.loads(result.terminal_text)
    assert parsed["passed"] is True


@pytest.mark.issue(976)
def test_cli_skill_publish_check_failure_blocks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from chirp.cli._skill_publish import collect_skill_publish_result

    app = _make_app()
    skill = Skill("unsigned", version="0.1.0", key_id="u1")

    @skill.tool("echo", description="Echo")
    def echo(message: str) -> dict[str, str]:
        return {"message": message}

    use_skill(app, skill)
    app_import = _register_app(monkeypatch, "_chirp_976_publish_unsigned", app)

    result = collect_skill_publish_result(app_import, fixture=True)
    assert result.exit_code == 1
    assert result["ok"] is False
    assert result["stages"][0]["passed"] is False
    assert len(result["stages"]) == 3
    assert "publish blocked" in result.terminal_text
