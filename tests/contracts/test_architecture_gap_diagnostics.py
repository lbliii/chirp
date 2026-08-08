"""Regression proof for the private architecture-gap projection (#885)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from chirp import App
from chirp.app.hypermedia_program import stable_identity
from chirp.config import AppConfig
from chirp.contracts import FragmentContract, check_hypermedia_surface, contract
from chirp.contracts.gap_diagnostics import (
    architecture_gap_report_to_dict,
    build_architecture_gap_report,
    format_architecture_gap_report,
)
from chirp.contracts.types import CheckResult, ContractIssue, Severity


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _freeze_program(app: App):
    app.freeze()
    program = app._runtime_state.hypermedia_program
    assert program is not None
    return program


@pytest.mark.issue(885)
def test_projects_existing_dead_orphan_unreachable_from_check_result() -> None:
    result = CheckResult(
        issues=[
            ContractIssue(
                Severity.WARNING,
                "dead",
                "Template 'unused.html' is not referenced by any route or template.",
                template="unused.html",
            ),
            ContractIssue(
                Severity.INFO,
                "orphan",
                "Route '/secret' is not referenced from any template.",
                route="/secret",
            ),
            ContractIssue(
                Severity.WARNING,
                "unreachable_block",
                "Block 'page_scripts' in 'page.html' is outside known composition roots.",
                template="page.html",
            ),
            ContractIssue(Severity.ERROR, "oob_registry", "unrelated finding"),
        ]
    )
    report = build_architecture_gap_report(None, result)

    by_kind = {gap.kind: gap for gap in report.gaps if gap.provenance == "check_result"}
    assert set(by_kind) == {"dead", "orphan", "unreachable_block"}
    assert by_kind["dead"].subject == "unused.html"
    assert by_kind["dead"].severity == Severity.WARNING.value
    assert "declare_template" in by_kind["dead"].repair
    assert by_kind["orphan"].observation == "unobserved"
    assert by_kind["orphan"].severity == Severity.INFO.value
    assert by_kind["unreachable_block"].severity == Severity.WARNING.value
    assert report.has_architecture_debt
    assert report.is_clean is False


@pytest.mark.issue(885)
def test_live_check_result_without_approved_debt_stays_clean_of_those_kinds(
    tmp_path: Path,
) -> None:
    (tmp_path / "index.html").write_text(
        "{% block content %}<h1>Home</h1>{% endblock %}", encoding="utf-8"
    )
    app = App(AppConfig(template_dir=str(tmp_path)))

    @app.route("/")
    @contract(returns=FragmentContract("index.html", "content"))
    async def home():
        return "ok"

    result = check_hypermedia_surface(app)
    report = build_architecture_gap_report(app._runtime_state.hypermedia_program, result)
    assert [gap for gap in report.gaps if gap.kind in {"dead", "orphan", "unreachable_block"}] == []
    assert report.has_architecture_debt is False


@pytest.mark.issue(885)
def test_orphan_and_unreachable_findings_project_without_severity_promotion() -> None:
    result = CheckResult(
        issues=[
            ContractIssue(
                Severity.INFO,
                "orphan",
                "Route '/secret' is not referenced from any template.",
                route="/secret",
            ),
            ContractIssue(
                Severity.WARNING,
                "unreachable_block",
                "Block 'page_scripts' in 'page.html' is outside known composition roots.",
                template="page.html",
            ),
        ]
    )
    report = build_architecture_gap_report(None, result)
    assert all(
        gap.severity != Severity.ERROR.value
        for gap in report.gaps
        if gap.kind in {"orphan", "unreachable_block"}
    )


@pytest.mark.issue(885)
def test_severity_overrides_are_suppressed_never_clean(tmp_path: Path) -> None:
    (tmp_path / "index.html").write_text("{% block content %}ok{% endblock %}", encoding="utf-8")
    app = App(AppConfig(template_dir=str(tmp_path), skip_contract_checks=True))

    @app.route("/")
    @contract(returns=FragmentContract("index.html", "content"))
    async def home():
        return "ok"

    app.override_contract_severity("dead", Severity.INFO)
    app.override_contract_severity("orphan", Severity.WARNING)
    result = check_hypermedia_surface(app)
    program = app._runtime_state.hypermedia_program
    overrides = dict(app._mutable_state.contract_severity_overrides)

    report = build_architecture_gap_report(
        program,
        result,
        severity_overrides=overrides,
    )

    suppressed = [gap for gap in report.gaps if gap.kind == "suppressed"]
    assert {gap.subject for gap in suppressed} == {"dead", "orphan"}
    assert all("does not decide whether" in (gap.details or "") for gap in suppressed)
    assert all("unsafe" in (gap.details or "") for gap in suppressed)
    assert report.has_suppressions
    assert report.is_clean is False
    assert "severity_overrides_are_suppressed_never_clean" in report.notes


@pytest.mark.issue(885)
def test_unresolved_enhancement_edge_is_unproven_not_error(tmp_path: Path) -> None:
    _write(
        tmp_path / "_layout.html",
        "<!doctype html><html><body>{% block page_root %}{% end %}</body></html>",
    )
    _write(
        tmp_path / "page.html",
        "{% extends '_layout.html' %}"
        "{% block page_root %}<section id='chart'>plain</section>{% end %}"
        "{% fragment chart_live enhancement='sse' fallback='missing_table' %}"
        "<section id='chart'>live</section>"
        "{% end %}",
    )
    app = App(AppConfig(template_dir=str(tmp_path), skip_contract_checks=True))

    @app.route("/", template="page.html")
    def index():
        return "ok"

    program = _freeze_program(app)
    unresolved = [edge for edge in program.enhancement_edges if not edge.resolved]
    assert unresolved

    report = build_architecture_gap_report(program, CheckResult())
    unproven = [gap for gap in report.gaps if gap.kind == "unproven"]
    assert len(unproven) == 1
    assert unproven[0].subject == unresolved[0].id
    assert unproven[0].severity is None
    assert unproven[0].reachability == "static_unresolved"
    assert report.is_clean is False
    assert "undeclared_dynamic_edges_remain_unproven" in report.notes


@pytest.mark.issue(885)
def test_declare_template_keeps_dynamic_surface_out_of_dead_debt(tmp_path: Path) -> None:
    (tmp_path / "index.html").write_text("{% block content %}home{% endblock %}", encoding="utf-8")
    (tmp_path / "plugin.html").write_text("{% block results %}rows{% endblock %}", encoding="utf-8")
    app = App(AppConfig(template_dir=str(tmp_path)))

    @app.route("/")
    @contract(returns=FragmentContract("index.html", "content"))
    async def home():
        return "ok"

    app.declare_template("plugin.html", blocks=("results",))
    result = check_hypermedia_surface(app)
    program = app._runtime_state.hypermedia_program

    report = build_architecture_gap_report(program, result)
    assert [gap for gap in report.gaps if gap.kind == "dead"] == []
    assert program is not None
    assert "plugin.html" in program.declared_template_names


@pytest.mark.issue(885)
def test_missing_checks_and_evidence_are_unobserved_not_clean_claims(
    tmp_path: Path,
) -> None:
    (tmp_path / "page.html").write_text("{% block page_root %}ok{% end %}", encoding="utf-8")
    app = App(AppConfig(template_dir=str(tmp_path), skip_contract_checks=True))

    @app.route("/", template="page.html")
    def home():
        return "ok"

    program = _freeze_program(app)

    unavailable = build_architecture_gap_report(program, None)
    assert unavailable.checks_available is False
    assert unavailable.behavioral_evidence == "unavailable"
    assert unavailable.is_clean is True  # no debt/suppression/unproven
    assert unavailable.is_complete is False
    assert {gap.subject for gap in unavailable.gaps if gap.kind == "unobserved"} == {
        "contract_findings",
        "behavioral_evidence",
    }

    with_empty_evidence = build_architecture_gap_report(
        program,
        CheckResult(),
        observed_transition_ids=frozenset(),
    )
    assert with_empty_evidence.behavioral_evidence == "present"
    assert with_empty_evidence.has_unobserved
    assert with_empty_evidence.is_complete is False
    assert "static_reachability_is_not_behavioral_coverage" in with_empty_evidence.notes

    observed = frozenset(edge.id for edge in program.transitions)
    complete = build_architecture_gap_report(
        program,
        CheckResult(),
        observed_transition_ids=observed,
    )
    assert complete.has_unobserved is False
    assert complete.is_clean is True
    assert complete.is_complete is True


@pytest.mark.issue(885)
def test_mounted_composition_preserves_declare_template_out_of_dead_debt(
    tmp_path: Path,
) -> None:
    parent_dir = tmp_path / "parent"
    child_dir = tmp_path / "child"
    parent_dir.mkdir()
    child_dir.mkdir()
    (parent_dir / "home.html").write_text(
        "{% block content %}parent{% endblock %}", encoding="utf-8"
    )
    (child_dir / "plugin.html").write_text(
        "{% block results %}rows{% endblock %}", encoding="utf-8"
    )

    parent = App(AppConfig(template_dir=str(parent_dir)))
    child = App(AppConfig(template_dir=str(child_dir), skip_contract_checks=True))

    @parent.route("/")
    @contract(returns=FragmentContract("home.html", "content"))
    async def home():
        return "ok"

    child.declare_template("plugin.html", blocks=("results",))
    parent.mount_app("/admin", child)

    result = check_hypermedia_surface(parent)
    program = parent._runtime_state.hypermedia_program
    report = build_architecture_gap_report(program, result)

    assert program is not None
    assert "plugin.html" in program.declared_template_names
    assert [gap for gap in report.gaps if gap.kind == "dead"] == []


@pytest.mark.issue(885)
def test_structured_and_terminal_parity_are_deterministic() -> None:
    result = CheckResult(
        issues=[
            ContractIssue(
                Severity.WARNING,
                "dead",
                "Template 'unused.html' is not referenced by any route or template.",
                template="unused.html",
            ),
            ContractIssue(
                Severity.INFO,
                "orphan",
                "Route '/side' is not referenced from any template.",
                route="/side",
            ),
        ]
    )
    overrides = {"dead": Severity.INFO}
    first = build_architecture_gap_report(
        None,
        result,
        severity_overrides=overrides,
        observed_transition_ids=None,
    )
    second = build_architecture_gap_report(
        None,
        result,
        severity_overrides=overrides,
        observed_transition_ids=None,
    )

    assert architecture_gap_report_to_dict(first) == architecture_gap_report_to_dict(second)
    assert format_architecture_gap_report(first) == format_architecture_gap_report(second)

    payload = architecture_gap_report_to_dict(first)
    terminal = format_architecture_gap_report(first)
    assert payload["is_clean"] is False
    assert payload["has_suppressions"] is True
    assert "unused.html" in terminal
    assert "/side" in terminal
    assert "suppressed" in terminal
    assert "repair:" in terminal
    assert json.loads(json.dumps(payload)) == payload
    assert stable_identity("transition", "a", "b").startswith("transition:")
