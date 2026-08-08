"""Proof for #975 — golden NL corpus + faithful-answer scorer."""

from __future__ import annotations

import pytest

from chirp import App
from chirp.skill import use_skill
from chirp.skill.smoke import (
    FAILURE_CATALOG,
    FAILURE_REFUSAL,
    FAILURE_SECTION_SKIP,
    FAILURE_UNFAITHFUL,
    FIXTURE_CORPUS,
    CorpusPrompt,
    make_fixture_skill,
    render_faithful_answer,
    run_smoke,
    score_answer,
)


def _make_app() -> App:
    app = App()

    @app.route("/")
    def index() -> str:
        return "ok"

    return app


@pytest.mark.issue(975)
class TestSkillSmokeHarnessIssue975:
    def test_scorer_passes_faithful_answer_on_fixture(self) -> None:
        skill = make_fixture_skill()
        app = _make_app()
        use_skill(app, skill)
        app.freeze()

        report = run_smoke(app, FIXTURE_CORPUS)
        assert report.passed, [(r.prompt_id, r.verdict) for r in report.failures]

        # Explicit faithful narration against weather engine JSON.
        engine = {"city": "Lisbon", "summary": "sunny", "temp_c": "22"}
        faithful = render_faithful_answer(FIXTURE_CORPUS[1], engine)
        verdict = score_answer(faithful, engine, required_facts=("Lisbon", "sunny"))
        assert verdict.passed
        assert verdict.failure_class is None

    def test_scorer_fails_refusal_catalog_and_section_skip(self) -> None:
        engine = {"city": "Lisbon", "summary": "sunny", "temp_c": "22"}

        refusal = score_answer(
            "I don't have data on that for Lisbon right now.",
            engine,
            required_facts=("Lisbon", "sunny"),
        )
        assert not refusal.passed
        assert refusal.failure_class == FAILURE_REFUSAL

        catalog = score_answer(
            "Here is what I can do: weather, echo, and portfolio tools.",
            engine,
            required_facts=("Lisbon", "sunny"),
        )
        assert not catalog.passed
        assert catalog.failure_class == FAILURE_CATALOG

        section_skip = score_answer(
            "Section did not run for the weather panel this turn.",
            engine,
            required_facts=("Lisbon", "sunny"),
        )
        assert not section_skip.passed
        assert section_skip.failure_class == FAILURE_SECTION_SKIP

        # Looks long enough but invents content unrelated to engine JSON.
        unfaithful = score_answer(
            "The market is closed today and no weather data was consulted.",
            engine,
            required_facts=("Lisbon", "sunny"),
        )
        assert not unfaithful.passed
        assert unfaithful.failure_class == FAILURE_UNFAITHFUL

    def test_run_smoke_rejects_injected_refusal_answer_fn(self) -> None:
        skill = make_fixture_skill()
        app = _make_app()
        use_skill(app, skill)
        app.freeze()

        def refuse(prompt: CorpusPrompt, _engine: object) -> str:
            return f"I don't have data on that regarding {prompt.tool}."

        report = run_smoke(app, FIXTURE_CORPUS[:1], answer_fn=refuse)
        assert not report.passed
        assert report.failures[0].verdict.failure_class == FAILURE_REFUSAL
