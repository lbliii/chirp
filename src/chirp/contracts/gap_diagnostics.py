"""Private architecture-gap projection for approved structural debt (#885).

This module copies facts that already exist in a frozen
:class:`~chirp.app.hypermedia_program.HypermediaProgram`, a finalized
:class:`~chirp.contracts.types.CheckResult`, and the author-declared severity
override map.  It does not accept an ``App``, does not rescan templates, does
not promote severities, and does not invent a second topology scanner.

Approved gap kinds (RFC 028 / issue #885):

- ``dead`` / ``orphan`` / ``unreachable_block`` — projected from existing check
  findings (architecture debt / unproven static navigation / composition gaps)
- ``suppressed`` — every severity override, never treated as clean coverage
- ``unproven`` — unresolved enhancement edges and the standing undeclared
  dynamic-selection caveat
- ``unobserved`` — missing or unmatched behavioral evidence; static reachability
  is never counted as behavioral coverage

This module is internal and is not exported from :mod:`chirp` or
:mod:`chirp.contracts`.  Its records are not a public inspection schema.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal, cast

from chirp.app.hypermedia_program import HypermediaProgram

from .types import CheckResult, ContractIssue, Severity

type GapKind = Literal[
    "dead",
    "orphan",
    "unreachable_block",
    "suppressed",
    "unproven",
    "unobserved",
]
type GapProvenance = Literal[
    "check_result",
    "severity_override",
    "compiler_edge",
    "analysis_policy",
    "runtime_evidence",
]
type GapReachability = Literal[
    "static_dead",
    "static_orphan",
    "static_unreachable",
    "static_unresolved",
    "policy_override",
    "dynamic_undeclared",
    "behavioral_unobserved",
    "evidence_unavailable",
]
type GapObservation = Literal[
    "not_applicable",
    "unobserved",
    "observed",
    "unavailable",
]

_FINDING_KINDS: frozenset[str] = frozenset({"dead", "orphan", "unreachable_block"})

_REPAIR: dict[GapKind, str] = {
    "dead": (
        "Reference the template from a route, include, import, or layout; remove "
        "it; or call app.declare_template(...) for a runtime-selected surface."
    ),
    "orphan": (
        "Reference the route from a template, mark it explicitly referenced, or "
        "accept that static navigation is unproven; prove reachability with an "
        "explicit route smoke or TestClient case."
    ),
    "unreachable_block": (
        "Nest the sibling page block under a recognized composing page root, or "
        "register it as a real fragment target."
    ),
    "suppressed": (
        "Review the severity override as deliberate application policy. It is "
        "visible architecture debt, not clean coverage; this report does not claim "
        "the override is stale."
    ),
    "unproven": (
        "Declare the missing template/block with app.declare_template(...), fix "
        "the unresolved fallback name, or add an explicit declaration for the "
        "runtime-selected edge."
    ),
    "unobserved": (
        "Run an explicit TestClient or browser case that names the transition. "
        "Static reachability is not behavioral coverage."
    ),
}

_NOTES = (
    "static_reachability_is_not_behavioral_coverage",
    "severity_overrides_are_suppressed_never_clean",
    "undeclared_dynamic_edges_remain_unproven",
)


@dataclass(frozen=True, slots=True)
class ArchitectureGap:
    """One projected architecture debt, suppression, or unknown."""

    kind: GapKind
    subject: str
    message: str
    provenance: GapProvenance
    reachability: GapReachability
    observation: GapObservation
    repair: str
    category: str | None = None
    severity: str | None = None
    details: str | None = None


@dataclass(frozen=True, slots=True)
class ArchitectureGapReport:
    """Deterministic inventory of approved architecture gaps.

    ``is_clean`` is True only when the report contains no debt findings, no
    severity overrides, no unproven dynamic edges, and no unobserved behavioral
    gaps.  Suppressions never make a report clean.
    """

    gaps: tuple[ArchitectureGap, ...]
    coverage: tuple[tuple[str, int], ...]
    notes: tuple[str, ...]
    checks_available: bool
    behavioral_evidence: Literal["unavailable", "present"]

    @property
    def is_clean(self) -> bool:
        """Return True only when no debt, suppression, or unproven edge remains.

        Unobserved behavioral gaps make the report incomplete; they do not by
        themselves invent architecture debt.  Suppressions always make
        ``is_clean`` False.
        """
        return not any(
            gap.kind in _FINDING_KINDS or gap.kind in {"suppressed", "unproven"}
            for gap in self.gaps
        )

    @property
    def is_complete(self) -> bool:
        """Return True when checks and behavioral evidence leave no unknowns."""
        return (
            self.checks_available
            and self.behavioral_evidence == "present"
            and not self.has_unobserved
            and self.is_clean
        )

    @property
    def has_suppressions(self) -> bool:
        return any(gap.kind == "suppressed" for gap in self.gaps)

    @property
    def has_architecture_debt(self) -> bool:
        return any(gap.kind in _FINDING_KINDS for gap in self.gaps)

    @property
    def has_unproven(self) -> bool:
        return any(gap.kind == "unproven" for gap in self.gaps)

    @property
    def has_unobserved(self) -> bool:
        return any(gap.kind == "unobserved" for gap in self.gaps)


def build_architecture_gap_report(
    program: HypermediaProgram | None,
    result: CheckResult | None,
    *,
    severity_overrides: Mapping[str, Severity] | None = None,
    observed_transition_ids: frozenset[str] | None = None,
) -> ArchitectureGapReport:
    """Project approved architecture gaps without changing check behavior.

    ``result`` may be ``None`` only when findings are unavailable; that state is
    an explicit unobserved gap, never a clean result.  ``observed_transition_ids``
    may be ``None`` when no runtime evidence snapshot was supplied; the report
    then records behavioral evidence as unavailable rather than inventing
    per-edge failures from static topology alone.
    """
    overrides = dict(severity_overrides or {})
    gaps: list[ArchitectureGap] = []

    if result is None:
        gaps.append(
            ArchitectureGap(
                kind="unobserved",
                subject="contract_findings",
                message=(
                    "Finalized contract findings are unavailable; architecture debt "
                    "cannot be proven clean from this projection alone."
                ),
                provenance="analysis_policy",
                reachability="evidence_unavailable",
                observation="unavailable",
                repair=_REPAIR["unobserved"],
                category=None,
                severity=None,
                details="Pass a finalized CheckResult after app.check().",
            )
        )
    else:
        gaps.extend(_project_finding_gaps(result.issues))

    gaps.extend(_project_suppressed_gaps(overrides))
    gaps.extend(_project_unproven_dynamic_gaps(program))
    gaps.extend(_project_unobserved_gaps(program, observed_transition_ids))

    ordered = tuple(
        sorted(
            gaps,
            key=lambda gap: (
                gap.kind,
                gap.category or "",
                gap.subject,
                gap.severity or "",
                gap.message,
                gap.details or "",
            ),
        )
    )
    return ArchitectureGapReport(
        gaps=ordered,
        coverage=_coverage(ordered),
        notes=_NOTES,
        checks_available=result is not None,
        behavioral_evidence=("unavailable" if observed_transition_ids is None else "present"),
    )


def architecture_gap_to_dict(gap: ArchitectureGap) -> dict[str, str | None]:
    """Serialize one gap for structured inspection consumers."""
    return {
        "kind": gap.kind,
        "subject": gap.subject,
        "message": gap.message,
        "provenance": gap.provenance,
        "reachability": gap.reachability,
        "observation": gap.observation,
        "repair": gap.repair,
        "category": gap.category,
        "severity": gap.severity,
        "details": gap.details,
    }


def architecture_gap_report_to_dict(report: ArchitectureGapReport) -> dict[str, object]:
    """Serialize a gap report with deterministic key order."""
    return {
        "behavioral_evidence": report.behavioral_evidence,
        "checks_available": report.checks_available,
        "coverage": dict(report.coverage),
        "gaps": [architecture_gap_to_dict(gap) for gap in report.gaps],
        "has_architecture_debt": report.has_architecture_debt,
        "has_suppressions": report.has_suppressions,
        "has_unobserved": report.has_unobserved,
        "has_unproven": report.has_unproven,
        "is_clean": report.is_clean,
        "is_complete": report.is_complete,
        "notes": list(report.notes),
    }


def format_architecture_gap_report(report: ArchitectureGapReport) -> str:
    """Render a stable terminal summary that mirrors the structured payload."""
    lines = [
        "Architecture gap report",
        f"clean={str(report.is_clean).lower()} "
        f"checks_available={str(report.checks_available).lower()} "
        f"behavioral_evidence={report.behavioral_evidence}",
        "coverage: "
        + ", ".join(f"{kind}={count}" for kind, count in report.coverage)
        + ("" if report.coverage else "(none)"),
    ]
    if not report.gaps:
        lines.append("gaps: (none)")
        return "\n".join(lines)

    lines.append("gaps:")
    for gap in report.gaps:
        location = gap.category or gap.kind
        lines.append(
            f"  [{gap.kind}/{location}] {gap.subject}: {gap.message} "
            f"(reachability={gap.reachability}; observation={gap.observation})"
        )
        lines.append(f"    repair: {gap.repair}")
        if gap.details:
            lines.append(f"    details: {gap.details}")
    lines.append("notes: " + ", ".join(report.notes))
    return "\n".join(lines)


def _project_finding_gaps(issues: list[ContractIssue]) -> list[ArchitectureGap]:
    gaps: list[ArchitectureGap] = []
    for issue in issues:
        if issue.category not in _FINDING_KINDS:
            continue
        kind = cast(GapKind, issue.category)
        subject = issue.template or issue.route or issue.category
        reachability: GapReachability
        observation: GapObservation
        if kind == "dead":
            reachability = "static_dead"
            observation = "not_applicable"
        elif kind == "orphan":
            reachability = "static_orphan"
            # Orphan routes are unproven static navigation, not behavioral proof.
            observation = "unobserved"
        else:
            reachability = "static_unreachable"
            observation = "not_applicable"
        gaps.append(
            ArchitectureGap(
                kind=kind,
                subject=subject,
                message=issue.message,
                provenance="check_result",
                reachability=reachability,
                observation=observation,
                repair=_REPAIR[kind],
                category=issue.category,
                severity=issue.severity.value,
                details=issue.details,
            )
        )
    return gaps


def _project_suppressed_gaps(overrides: Mapping[str, Severity]) -> list[ArchitectureGap]:
    gaps: list[ArchitectureGap] = []
    for category, severity in sorted(overrides.items()):
        gaps.append(
            ArchitectureGap(
                kind="suppressed",
                subject=category,
                message=(
                    f"Severity override is active for category {category!r} "
                    f"(effective severity={severity.value})."
                ),
                provenance="severity_override",
                reachability="policy_override",
                observation="not_applicable",
                repair=_REPAIR["suppressed"],
                category=category,
                severity=severity.value,
                details=(
                    "Override inventory only; this projection does not decide whether "
                    "the override is outdated or unsafe."
                ),
            )
        )
    return gaps


def _project_unproven_dynamic_gaps(
    program: HypermediaProgram | None,
) -> list[ArchitectureGap]:
    """Project concrete unproven dynamic edges from compiler facts.

    The standing caveat that undeclared runtime template selection remains
    outside static reachability lives in :data:`_NOTES` so every app is not
    forced into a permanent ``unproven`` finding.  Concrete unresolved
    enhancement fallback edges are projected here.
    """
    if program is None:
        return []

    gaps: list[ArchitectureGap] = []
    for edge in program.enhancement_edges:
        if edge.resolved:
            continue
        gaps.append(
            ArchitectureGap(
                kind="unproven",
                subject=edge.id,
                message=(
                    "Enhancement fallback edge is unresolved in the frozen HypermediaProgram."
                ),
                provenance="compiler_edge",
                reachability="static_unresolved",
                observation="unobserved",
                repair=_REPAIR["unproven"],
                category="enhancement_fallback",
                severity=None,
                details=(
                    f"enhanced={edge.enhanced_block_id}; "
                    f"fallback={edge.fallback_block_id}; "
                    f"origin={edge.origin.identifier}"
                ),
            )
        )
    return gaps


def _project_unobserved_gaps(
    program: HypermediaProgram | None,
    observed_transition_ids: frozenset[str] | None,
) -> list[ArchitectureGap]:
    if observed_transition_ids is None:
        return [
            ArchitectureGap(
                kind="unobserved",
                subject="behavioral_evidence",
                message=(
                    "No runtime evidence snapshot was supplied; compiled transitions "
                    "are not claimed as behaviorally covered."
                ),
                provenance="runtime_evidence",
                reachability="evidence_unavailable",
                observation="unavailable",
                repair=_REPAIR["unobserved"],
                category=None,
                severity=None,
                details="Pass observed_transition_ids from an evidence overlay when available.",
            )
        ]

    if program is None:
        return [
            ArchitectureGap(
                kind="unobserved",
                subject="hypermedia_program",
                message=(
                    "Behavioral evidence was supplied without a HypermediaProgram; "
                    "transition observation cannot be correlated."
                ),
                provenance="runtime_evidence",
                reachability="evidence_unavailable",
                observation="unavailable",
                repair=_REPAIR["unobserved"],
            )
        ]

    gaps: list[ArchitectureGap] = []
    for edge in program.transitions:
        if edge.id in observed_transition_ids:
            continue
        gaps.append(
            ArchitectureGap(
                kind="unobserved",
                subject=edge.id,
                message=(
                    "Compiled transition has no matching retained runtime observation "
                    "in the supplied evidence snapshot."
                ),
                provenance="runtime_evidence",
                reachability="behavioral_unobserved",
                observation="unobserved",
                repair=_REPAIR["unobserved"],
                category=edge.kind,
                severity=None,
                details=(
                    f"source={edge.source_id}; destination={edge.destination_id}; "
                    f"resolved={str(edge.resolved).lower()}"
                ),
            )
        )
    return gaps


def _coverage(
    gaps: tuple[ArchitectureGap, ...] | list[ArchitectureGap],
) -> tuple[tuple[str, int], ...]:
    counts = dict.fromkeys(
        ("dead", "orphan", "unreachable_block", "suppressed", "unproven", "unobserved"),
        0,
    )
    for gap in gaps:
        counts[gap.kind] = counts.get(gap.kind, 0) + 1
    return tuple(sorted((kind, count) for kind, count in counts.items() if count))
