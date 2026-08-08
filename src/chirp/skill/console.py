"""Hypermedia skill console — registry browse, detail, reliability score.

Human face for an Orrery-style host: ``Page``/``Fragment`` list + detail
pages over a mounted :class:`~chirp.skill.registry.SkillRegistry`. Machine
discovery stays on :func:`~chirp.skill.registry.mount_skills`; this module
does not own live invocation SSE (#983) — that plugs in via the live-log DOM
hook. Env-var key presence plugs in via ``key_status`` (pass
:meth:`~chirp.skill.keystore.EnvKeystore.as_key_status_fn`).
"""

from __future__ import annotations

import threading
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal

from kida import PackageLoader

from chirp.errors import NotFound
from chirp.skill.manifest import Manifest
from chirp.skill.registry import SkillRegistry
from chirp.templating.returns import Page

if TYPE_CHECKING:
    from chirp.app import App
    from chirp.skill.smoke import SmokeReport

DEFAULT_CONSOLE_PATH = "/console"
_TEMPLATE_NS = "chirp_skill"

ReliabilityStatus = Literal["pass", "fail", "unknown"]

#: ``key_status(skill_name, provider_key_names) -> {name: present|None}``.
#: ``None`` means unscored (no keystore wired yet — #984).
KeyStatusFn = Callable[[str, tuple[str, ...]], Mapping[str, bool | None]]


@dataclass(frozen=True, slots=True)
class ReliabilityScore:
    """Smoke-derived reliability for one skill (publish-oracle pass rate)."""

    passed: int
    total: int
    status: ReliabilityStatus

    @classmethod
    def unknown(cls) -> ReliabilityScore:
        return cls(passed=0, total=0, status="unknown")

    @classmethod
    def from_smoke(cls, report: SmokeReport) -> ReliabilityScore:
        total = len(report.results)
        passed = sum(1 for r in report.results if r.verdict.passed)
        if total == 0:
            return cls.unknown()
        status: ReliabilityStatus = "pass" if report.passed else "fail"
        return cls(passed=passed, total=total, status=status)

    @property
    def ratio(self) -> float | None:
        if self.total == 0:
            return None
        return self.passed / self.total

    @property
    def label(self) -> str:
        if self.status == "unknown":
            return "unscored"
        return f"{self.passed}/{self.total} {self.status}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "total": self.total,
            "status": self.status,
            "ratio": self.ratio,
            "label": self.label,
        }


@dataclass
class ReliabilityStore:
    """Mutable map of skill name → :class:`ReliabilityScore`.

    Thread-safe for concurrent ``record`` during setup / smoke runs.
    """

    _scores: dict[str, ReliabilityScore] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def record(
        self,
        skill_name: str,
        report: SmokeReport | ReliabilityScore,
    ) -> ReliabilityScore:
        """Store a smoke report or score under ``skill_name``; return the score."""
        score = (
            report if isinstance(report, ReliabilityScore) else ReliabilityScore.from_smoke(report)
        )
        with self._lock:
            self._scores[skill_name] = score
        return score

    def get(self, skill_name: str) -> ReliabilityScore:
        with self._lock:
            return self._scores.get(skill_name, ReliabilityScore.unknown())

    def as_mapping(self) -> Mapping[str, ReliabilityScore]:
        with self._lock:
            return dict(self._scores)


@dataclass(frozen=True, slots=True)
class ContractSummary:
    """Human-facing contract snapshot for the skill detail page."""

    ok: bool
    has_signing_key: bool
    public_key_present: bool
    content_digest_present: bool
    tool_count: int
    issues: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "has_signing_key": self.has_signing_key,
            "public_key_present": self.public_key_present,
            "content_digest_present": self.content_digest_present,
            "tool_count": self.tool_count,
            "issues": list(self.issues),
        }


@dataclass(frozen=True, slots=True)
class KeyStatusRow:
    """One provider-key row (name only; never secret values)."""

    name: str
    present: bool | None

    @property
    def label(self) -> str:
        if self.present is True:
            return "present"
        if self.present is False:
            return "missing"
        return "unknown"

    @property
    def badge_class(self) -> str:
        if self.present is True:
            return "pass"
        if self.present is False:
            return "fail"
        return "unknown"


def contract_summary_for_skill(skill: Any, *, env: str = "development") -> ContractSummary:
    """Evaluate ``skill_contract`` for a live skill (detail-page context)."""
    from chirp.contracts.rules_skill_contract import (
        check_skill_contract,
        skill_record_from_skill,
    )

    record = skill_record_from_skill(skill)
    # Prefer freeze-finalized manifest fields when available.
    try:
        manifest = skill.manifest
        public_key = manifest.public_key
        content_digest = manifest.content_digest
    except RuntimeError:
        public_key = record.public_key
        content_digest = record.content_digest

    issues = check_skill_contract(
        (record,),
        scope_registry=frozenset(),
        env=env,
        has_auth_middleware=True,  # avoid noise on the console; mount already gates
    )
    messages = tuple(i.message for i in issues)
    public_ok = bool(public_key)
    digest_ok = bool(content_digest)
    ok = record.has_signing_key and public_ok and digest_ok and not messages
    return ContractSummary(
        ok=ok,
        has_signing_key=record.has_signing_key,
        public_key_present=public_ok,
        content_digest_present=digest_ok,
        tool_count=len(record.tools),
        issues=messages,
    )


def key_status_rows(
    skill_name: str,
    provider_keys: tuple[str, ...],
    key_status: KeyStatusFn | None,
) -> tuple[KeyStatusRow, ...]:
    """Build key-management rows; secrets never appear (hook for #984)."""
    if not provider_keys:
        return ()
    status_map: Mapping[str, bool | None] = {}
    if key_status is not None:
        status_map = key_status(skill_name, provider_keys)
    return tuple(
        KeyStatusRow(name=name, present=status_map.get(name) if key_status else None)
        for name in provider_keys
    )


def _normalize_console_path(path: str) -> str:
    if not isinstance(path, str) or not path.strip():
        msg = "console_path must be a non-empty string"
        raise ValueError(msg)
    normalized = path.strip()
    if not normalized.startswith("/"):
        normalized = "/" + normalized
    if len(normalized) > 1 and normalized.endswith("/"):
        normalized = normalized.rstrip("/")
    return normalized


def _coerce_scores(
    scores: ReliabilityStore | Mapping[str, ReliabilityScore | SmokeReport] | None,
) -> ReliabilityStore:
    if scores is None:
        return ReliabilityStore()
    if isinstance(scores, ReliabilityStore):
        return scores
    store = ReliabilityStore()
    for name, value in scores.items():
        store.record(name, value)
    return store


def _list_entries(
    registry: SkillRegistry,
    scores: ReliabilityStore,
    console_path: str,
) -> tuple[dict[str, Any], ...]:
    entries: list[dict[str, Any]] = []
    for skill in registry.skills():
        try:
            manifest = skill.manifest
        except RuntimeError:
            manifest = skill.assemble_manifest()
        score = scores.get(skill.name)
        entries.append(
            {
                "name": skill.name,
                "version": manifest.version,
                "tools": list(manifest.tools),
                "content_digest": manifest.content_digest,
                "provider_keys": list(manifest.provider_keys),
                "reliability": score,
                "href": f"{console_path}/{skill.name}",
            }
        )
    return tuple(entries)


def _detail_context(
    *,
    app: App,
    registry: SkillRegistry,
    skill_name: str,
    scores: ReliabilityStore,
    key_status: KeyStatusFn | None,
    console_path: str,
) -> dict[str, Any]:
    skill = registry.get(skill_name)
    if skill is None:
        raise NotFound(f"Skill {skill_name!r} is not registered")

    try:
        manifest: Manifest = skill.manifest
    except RuntimeError:
        manifest = skill.assemble_manifest()

    contract = contract_summary_for_skill(skill, env=getattr(app.config, "env", "development"))
    reliability = scores.get(skill.name)
    keys = key_status_rows(skill.name, manifest.provider_keys, key_status)

    return {
        "skill_name": skill.name,
        "manifest": manifest,
        "contract": contract,
        "reliability": reliability,
        "keys": keys,
        "keystore_wired": key_status is not None,
        "console_path": console_path,
        "list_href": console_path,
        # Integration point for #983 — empty live-log region in the template.
        "live_log_ready": False,
    }


def mount_console(
    app: App,
    registry: SkillRegistry,
    *,
    console_path: str = DEFAULT_CONSOLE_PATH,
    scores: ReliabilityStore | Mapping[str, ReliabilityScore | SmokeReport] | None = None,
    key_status: KeyStatusFn | None = None,
) -> str:
    """Register hypermedia browse + skill detail routes for ``registry``.

    Returns the normalized console path. Templates load via
    ``PackageLoader("chirp.skill", "templates")``.

    ``scores`` supplies smoke-derived :class:`ReliabilityScore` values (or a
    live :class:`ReliabilityStore`). ``key_status`` is an optional #984 hook
    that reports provider-key *presence* only — never secret values.
    """
    if not isinstance(registry, SkillRegistry):
        msg = "mount_console() requires a chirp.skill.SkillRegistry"
        raise TypeError(msg)

    path = _normalize_console_path(console_path)
    store = _coerce_scores(scores)

    app.add_loader(PackageLoader("chirp.skill", "templates"))

    @app.route(path, methods=["GET"], name="chirp_skill_console_list")
    def console_list() -> Page:
        return Page(
            f"{_TEMPLATE_NS}/console_list.html",
            "skill_list",
            console_path=path,
            skills=_list_entries(registry, store, path),
        )

    @app.route(f"{path}/{{skill_name}}", methods=["GET"], name="chirp_skill_console_detail")
    def console_detail(skill_name: str) -> Page:
        ctx = _detail_context(
            app=app,
            registry=registry,
            skill_name=skill_name,
            scores=store,
            key_status=key_status,
            console_path=path,
        )
        return Page(
            f"{_TEMPLATE_NS}/console_detail.html",
            "skill_detail",
            **ctx,
        )

    return path


__all__ = [
    "DEFAULT_CONSOLE_PATH",
    "ContractSummary",
    "KeyStatusFn",
    "KeyStatusRow",
    "ReliabilityScore",
    "ReliabilityStore",
    "contract_summary_for_skill",
    "key_status_rows",
    "mount_console",
]
