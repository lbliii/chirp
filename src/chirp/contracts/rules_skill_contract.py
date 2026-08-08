"""``skill_contract`` — mounted skills must be signable, scoped, and complete (#972).

Flags at ``app.check()``:

- Envelope tools without a signing private key → always **ERROR**
- Tool scopes absent from ``app.register_scope`` (when a scope registry exists)
  → env-aware (ERROR production / WARNING staging / silent development), same
  registry-backed idiom as ``auth_spec``
- Any scoped tool with no ``AuthMiddleware`` → env-aware (scopes resolve via
  the auth user ContextVar)
- Incomplete freeze-time manifest (empty tools / public key / content digest)
  → always **ERROR**

Registered from :func:`chirp.skill.mount.use_skill` via
``app.register_contract_check`` (chirp_ui pattern). Middleware / env are read
from the live app because :class:`~chirp.app.state.ContractCheckSnapshot`
does not expose them to plugin checks.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from chirp.contracts.types import CheckResult, ContractIssue, Severity

if TYPE_CHECKING:
    from chirp.app.state import ContractCheckSnapshot

_AUTH_MIDDLEWARE = "AuthMiddleware"
_SKILLS_EXTRA_KEY = "skills"


@dataclass(frozen=True, slots=True)
class SkillContractRecord:
    """Serializable skill descriptor stored in ``extras['skills']``."""

    name: str
    version: str
    has_signing_key: bool
    tools: tuple[tuple[str, tuple[str, ...]], ...]
    public_key: str = ""
    content_digest: str = ""
    manifest_complete: bool | None = None


def _env_severity(env: str) -> Severity | None:
    """Return env-aware severity, or ``None`` to stay silent (development)."""
    if env == "production":
        return Severity.ERROR
    if env == "staging":
        return Severity.WARNING
    return None


def _middleware_class_names(middleware_list: Sequence[Any]) -> set[str]:
    return {type(mw).__name__ for mw in middleware_list}


def check_skill_contract(
    skills: Sequence[SkillContractRecord],
    *,
    scope_registry: frozenset[str],
    env: str = "development",
    has_auth_middleware: bool = False,
) -> list[ContractIssue]:
    """Evaluate skill contract records and return issues (pure; unit-testable)."""
    issues: list[ContractIssue] = []
    if not skills:
        return issues

    env_sev = _env_severity(env)
    scoped_tool_seen = False

    for skill in skills:
        if not skill.has_signing_key:
            issues.append(
                ContractIssue(
                    severity=Severity.ERROR,
                    category="skill_contract",
                    message=(
                        f"Skill {skill.name!r} mounts envelope tools without a signing "
                        "private key. Pass private_key= to Skill(...) so tool results "
                        "can be signed."
                    ),
                    details="Repair surface: Skill(..., private_key=...).",
                )
            )

        for tool_name, scopes in skill.tools:
            if not scopes:
                continue
            scoped_tool_seen = True
            if scope_registry and env_sev is not None:
                issues.extend(
                    ContractIssue(
                        severity=env_sev,
                        category="skill_contract",
                        message=(
                            f"Skill {skill.name!r} tool {tool_name!r} requires "
                            f"scope {scope!r}, which is not a registered scope "
                            f"while env={env!r}. Declare it with "
                            "app.register_scope(name) or fix the typo; an "
                            "unknown scope silently 403s."
                        ),
                        details=(
                            "Repair surface: app.register_scope(...) or "
                            "@skill.tool(..., scopes=...)."
                        ),
                    )
                    for scope in scopes
                    if scope not in scope_registry
                )

        # Missing signing key already covers the empty-key stub; only flag
        # incomplete manifests when a key was provided but freeze-time fields
        # are still absent/malformed.
        incomplete = skill.has_signing_key and (
            skill.manifest_complete is False
            or (
                skill.manifest_complete is None
                and (
                    not skill.tools
                    or not skill.public_key
                    or not skill.content_digest
                    or not skill.content_digest.startswith("sha256:")
                )
            )
        )
        if incomplete:
            issues.append(
                ContractIssue(
                    severity=Severity.ERROR,
                    category="skill_contract",
                    message=(
                        f"Skill {skill.name!r} has an incomplete freeze-time manifest "
                        "(missing tools, public_key, or content_digest). Mount tools "
                        "with @skill.tool, provide a signing key / public key, and "
                        "call app.freeze() / app.check() so the content digest is "
                        "published."
                    ),
                    details="Repair surface: Skill.tool / use_skill / app.freeze().",
                )
            )

    if scoped_tool_seen and not has_auth_middleware and env_sev is not None:
        issues.append(
            ContractIssue(
                severity=env_sev,
                category="skill_contract",
                message=(
                    f"A mounted skill declares tool scopes but no AuthMiddleware is "
                    f"registered while env={env!r}. Scoped skill tools call "
                    "enforce_auth, which reads the auth user ContextVar — without "
                    "AuthMiddleware every call sees AnonymousUser and scoped tools "
                    "403. Register AuthMiddleware after SessionMiddleware."
                ),
                details="Repair surface: AuthMiddleware registration.",
            )
        )

    return issues


def _records_from_extras(extras: dict[str, Any]) -> tuple[SkillContractRecord, ...]:
    raw = extras.get(_SKILLS_EXTRA_KEY)
    if not raw:
        return ()
    records: list[SkillContractRecord] = []
    for item in raw:
        if isinstance(item, SkillContractRecord):
            records.append(item)
        elif isinstance(item, dict):
            records.append(
                SkillContractRecord(
                    name=str(item["name"]),
                    version=str(item.get("version", "")),
                    has_signing_key=bool(item.get("has_signing_key")),
                    tools=tuple(
                        (str(name), tuple(str(s) for s in scopes))
                        for name, scopes in item.get("tools", ())
                    ),
                    public_key=str(item.get("public_key", "")),
                    content_digest=str(item.get("content_digest", "")),
                    manifest_complete=item.get("manifest_complete"),
                )
            )
    return tuple(records)


def _enrich_from_live_skills(
    records: tuple[SkillContractRecord, ...],
    domains: Sequence[Any],
) -> tuple[SkillContractRecord, ...]:
    """Overlay freeze-time manifest fields from live ``Skill`` domains when present."""
    by_name: dict[str, Any] = {}
    for domain in domains:
        name = getattr(domain, "name", None)
        if isinstance(name, str) and hasattr(domain, "assemble_manifest"):
            by_name[name] = domain
    if not by_name:
        return records

    enriched: list[SkillContractRecord] = []
    for record in records:
        skill = by_name.get(record.name)
        if skill is None:
            enriched.append(record)
            continue
        try:
            manifest = skill.manifest
        except RuntimeError:
            enriched.append(record)
            continue
        complete = bool(
            manifest.tools and manifest.public_key and manifest.content_digest.startswith("sha256:")
        )
        enriched.append(
            SkillContractRecord(
                name=record.name,
                version=record.version,
                has_signing_key=record.has_signing_key,
                tools=record.tools,
                public_key=manifest.public_key,
                content_digest=manifest.content_digest,
                manifest_complete=complete,
            )
        )
    return tuple(enriched)


@dataclass(slots=True)
class SkillContractCheck:
    """Plugin check registered by ``use_skill`` — holds the app for env/middleware."""

    _app: Any

    def __call__(self, snapshot: ContractCheckSnapshot, result: CheckResult) -> None:
        records = _records_from_extras(snapshot.extras)
        if not records:
            return
        domains = getattr(getattr(self._app, "_mutable_state", None), "pending_domains", ())
        records = _enrich_from_live_skills(records, domains)
        middleware = getattr(getattr(self._app, "_mutable_state", None), "middleware", [])
        env = getattr(getattr(self._app, "config", None), "env", "development")
        result.issues.extend(
            check_skill_contract(
                records,
                scope_registry=snapshot.scope_registry,
                env=env,
                has_auth_middleware=_AUTH_MIDDLEWARE in _middleware_class_names(middleware),
            )
        )


def skill_record_from_skill(skill: Any) -> SkillContractRecord:
    """Build a :class:`SkillContractRecord` from a live :class:`~chirp.skill.Skill`."""
    pending = getattr(skill, "_pending", ())
    tools = tuple((t.name, tuple(t.scopes)) for t in pending)
    private_key = getattr(skill, "_private_key", None)
    public_key = ""
    content_digest = ""
    manifest_complete: bool | None = None
    manifest = getattr(skill, "_manifest", None)
    if manifest is not None:
        public_key = getattr(manifest, "public_key", "") or ""
        content_digest = getattr(manifest, "content_digest", "") or ""
        manifest_complete = bool(
            getattr(manifest, "tools", ()) and public_key and content_digest.startswith("sha256:")
        )
    return SkillContractRecord(
        name=skill.name,
        version=skill.version,
        has_signing_key=private_key is not None,
        tools=tools,
        public_key=public_key,
        content_digest=content_digest,
        manifest_complete=manifest_complete,
    )


__all__ = [
    "SkillContractCheck",
    "SkillContractRecord",
    "check_skill_contract",
    "skill_record_from_skill",
]
