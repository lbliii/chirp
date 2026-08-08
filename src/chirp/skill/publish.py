"""Skill publish gate — check + freeze + smoke with a pass/fail receipt.

Orrery publish oracle (epic #962 / issue #976): a skill may publish only when
``app.check()`` contracts, freeze-time manifest digests, and the smoke harness
all pass. This module orchestrates the three stages and always runs all three
so the receipt reports every stage; any failure blocks publish.

No registry upload lives here (E5).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from chirp.contracts.checker import check_hypermedia_surface
from chirp.skill.mount import Skill
from chirp.skill.smoke import AnswerFn, CorpusPrompt, SmokeReport, run_smoke

STAGE_CHECK = "check"
STAGE_FREEZE = "freeze"
STAGE_SMOKE = "smoke"


@dataclass(frozen=True, slots=True)
class StageResult:
    """Outcome of one publish-gate stage."""

    name: str
    passed: bool
    summary: str
    detail: Mapping[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class PublishReceipt:
    """Legible pass/fail receipt for ``chirp skill publish`` / :func:`run_publish_gate`."""

    passed: bool
    stages: tuple[StageResult, ...]
    manifests: tuple[dict[str, str], ...] = ()
    smoke: SmokeReport | None = None

    @property
    def failures(self) -> tuple[StageResult, ...]:
        return tuple(s for s in self.stages if not s.passed)

    def to_dict(self) -> dict[str, Any]:
        """Stable JSON-serializable receipt payload."""
        return {
            "ok": self.passed,
            "passed": self.passed,
            "stages": [
                {
                    "name": s.name,
                    "passed": s.passed,
                    "summary": s.summary,
                    "detail": dict(s.detail) if s.detail is not None else None,
                }
                for s in self.stages
            ],
            "manifests": [dict(m) for m in self.manifests],
            "smoke": None
            if self.smoke is None
            else {
                "passed": self.smoke.passed,
                "results": [
                    {
                        "prompt_id": r.prompt_id,
                        "tool": r.tool,
                        "passed": r.verdict.passed,
                        "reason": r.verdict.reason,
                        "failure_class": r.verdict.failure_class,
                    }
                    for r in self.smoke.results
                ],
            },
        }


def format_publish_receipt(receipt: PublishReceipt) -> str:
    """Human-readable multi-stage publish receipt for the terminal."""
    lines = ["chirp skill publish", ""]
    for stage in receipt.stages:
        mark = "PASS" if stage.passed else "FAIL"
        lines.append(f"  [{mark}] {stage.name}: {stage.summary}")
    lines.append("")
    if receipt.manifests:
        lines.append("  manifests:")
        for item in receipt.manifests:
            digest = item.get("content_digest") or "(missing)"
            lines.append(f"    - {item.get('name', '?')}@{item.get('version', '?')} {digest}")
        lines.append("")
    if receipt.passed:
        lines.append("  ✓ publish gate passed")
    else:
        failed = ", ".join(s.name for s in receipt.failures) or "(unknown)"
        lines.append(f"  ✗ publish blocked — failing stage(s): {failed}")
    return "\n".join(lines) + "\n"


def _iter_skills(app: Any) -> tuple[Skill, ...]:
    domains = getattr(getattr(app, "_mutable_state", None), "pending_domains", ())
    return tuple(d for d in domains if isinstance(d, Skill))


def _check_stage(app: Any, *, warnings_as_errors: bool) -> StageResult:
    result = check_hypermedia_surface(app)
    error_count = len(result.errors)
    warning_count = len(result.warnings)
    failed = bool(result.errors) or (warnings_as_errors and bool(result.warnings))
    categories = sorted({issue.category for issue in result.errors})
    summary = f"{error_count} error(s), {warning_count} warning(s)" + (
        f" — {', '.join(categories)}" if categories else ""
    )
    if not failed and error_count == 0:
        summary = f"ok ({warning_count} warning(s))" if warning_count else "ok"
    return StageResult(
        name=STAGE_CHECK,
        passed=not failed,
        summary=summary,
        detail={
            "errors": error_count,
            "warnings": warning_count,
            "categories": categories,
        },
    )


def _freeze_stage(app: Any) -> tuple[StageResult, tuple[dict[str, str], ...]]:
    app.freeze()
    skills = _iter_skills(app)
    manifests: list[dict[str, str]] = []
    problems: list[str] = []

    if not skills:
        problems.append("no skills mounted via use_skill()")

    for skill in skills:
        try:
            manifest = skill.manifest
        except RuntimeError as exc:
            problems.append(f"{skill.name}: {exc}")
            continue
        entry = {
            "name": manifest.name,
            "version": manifest.version,
            "content_digest": manifest.content_digest,
            "public_key": manifest.public_key,
        }
        manifests.append(entry)
        if not manifest.content_digest:
            problems.append(f"{skill.name}: empty content_digest (incomplete signing key?)")
        if not manifest.public_key:
            problems.append(f"{skill.name}: empty public_key")

    passed = not problems
    summary = f"{len(manifests)} skill manifest(s) finalized" if passed else "; ".join(problems)
    return (
        StageResult(
            name=STAGE_FREEZE,
            passed=passed,
            summary=summary,
            detail={"problems": problems, "skill_count": len(skills)},
        ),
        tuple(manifests),
    )


def _smoke_stage(
    app: Any,
    corpus: Sequence[CorpusPrompt],
    *,
    answer_fn: AnswerFn | None,
) -> tuple[StageResult, SmokeReport | None]:
    if not corpus:
        return (
            StageResult(
                name=STAGE_SMOKE,
                passed=False,
                summary="corpus is empty",
                detail={"prompt_count": 0},
            ),
            None,
        )
    try:
        report = run_smoke(app, corpus, answer_fn=answer_fn)
    except Exception as exc:
        # Broad catch: the gate must always emit a smoke stage in the receipt.
        return (
            StageResult(
                name=STAGE_SMOKE,
                passed=False,
                summary=f"smoke raised {type(exc).__name__}: {exc}",
                detail={"error": str(exc)},
            ),
            None,
        )
    failures = report.failures
    if report.passed:
        summary = f"{len(report.results)} prompt(s) faithful"
    else:
        bits = [
            f"{f.prompt_id}/{f.tool}:{f.verdict.failure_class or f.verdict.reason}"
            for f in failures
        ]
        summary = f"{len(failures)} failure(s) — " + "; ".join(bits)
    return (
        StageResult(
            name=STAGE_SMOKE,
            passed=report.passed,
            summary=summary,
            detail={
                "prompt_count": len(report.results),
                "failure_count": len(failures),
            },
        ),
        report,
    )


def run_publish_gate(
    app: Any,
    corpus: Sequence[CorpusPrompt],
    *,
    answer_fn: AnswerFn | None = None,
    warnings_as_errors: bool = False,
) -> PublishReceipt:
    """Run check → freeze → smoke and return a receipt.

    All three stages always execute so the receipt is complete. Publish is
    blocked when any stage fails (``receipt.passed`` is False).
    """
    check = _check_stage(app, warnings_as_errors=warnings_as_errors)
    freeze, manifests = _freeze_stage(app)
    smoke, report = _smoke_stage(app, corpus, answer_fn=answer_fn)
    stages = (check, freeze, smoke)
    return PublishReceipt(
        passed=all(s.passed for s in stages),
        stages=stages,
        manifests=manifests,
        smoke=report,
    )


__all__ = [
    "STAGE_CHECK",
    "STAGE_FREEZE",
    "STAGE_SMOKE",
    "PublishReceipt",
    "StageResult",
    "format_publish_receipt",
    "run_publish_gate",
]
