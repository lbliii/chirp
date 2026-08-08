"""Skill registry — manifest-indexed multi-skill mount for Orrery-style apps.

A :class:`SkillRegistry` stores skills by name, mounts each via
:func:`~chirp.skill.mount.use_skill` onto one app (aggregated ``/mcp``), and
exposes a discovery route that lists frozen manifests.

Console UI and keystore live in sibling issues — this module is the
machine-facing registry + discovery surface only.
"""

from __future__ import annotations

import threading
from collections.abc import Iterable, Iterator, Mapping
from typing import TYPE_CHECKING, Any

from chirp.skill.manifest import Manifest
from chirp.skill.mount import Skill, use_skill

if TYPE_CHECKING:
    from chirp.app import App

DEFAULT_DISCOVERY_PATH = "/skills"


class SkillRegistry:
    """Manifest-indexed store of skills to mount onto a single Chirp app.

    Setup-only mutation (``add``) until :meth:`mount` / :func:`mount_skills`
    runs; afterwards the registry is read-only. Thread-safe for concurrent
    setup registration (free-threading).

    After the app freezes, :meth:`manifests` returns the immutable content-
    digested manifests finalized by each skill's freeze-time domain hook.
    """

    __slots__ = ("_discovery_path", "_lock", "_mounted", "_skills")

    def __init__(self) -> None:
        self._skills: dict[str, Skill] = {}
        self._mounted = False
        self._discovery_path: str | None = None
        self._lock = threading.Lock()

    @property
    def mounted(self) -> bool:
        """True after :meth:`mount` / :func:`mount_skills` has run."""
        with self._lock:
            return self._mounted

    @property
    def discovery_path(self) -> str | None:
        """Path of the discovery route once mounted; ``None`` until then."""
        with self._lock:
            return self._discovery_path

    @property
    def names(self) -> frozenset[str]:
        with self._lock:
            return frozenset(self._skills)

    def __len__(self) -> int:
        with self._lock:
            return len(self._skills)

    def __contains__(self, name: object) -> bool:
        if not isinstance(name, str):
            return False
        with self._lock:
            return name in self._skills

    def __iter__(self) -> Iterator[Skill]:
        with self._lock:
            skills = tuple(self._skills.values())
        yield from skills

    def add(self, skill: Skill) -> None:
        """Register ``skill`` by name. Fail loud on duplicates or post-mount."""
        if not isinstance(skill, Skill):
            msg = "SkillRegistry.add() requires a chirp.skill.Skill instance"
            raise TypeError(msg)
        with self._lock:
            if self._mounted:
                msg = "Cannot add skills after mount_skills() / SkillRegistry.mount()"
                raise RuntimeError(msg)
            if skill.name in self._skills:
                msg = f"Skill {skill.name!r} is already registered"
                raise ValueError(msg)
            self._skills[skill.name] = skill

    def get(self, name: str) -> Skill | None:
        """Return the registered skill named ``name``, or ``None``."""
        with self._lock:
            return self._skills.get(name)

    def skills(self) -> tuple[Skill, ...]:
        """Return registered skills in registration order."""
        with self._lock:
            return tuple(self._skills.values())

    def manifests(self) -> tuple[Manifest, ...]:
        """Return manifests for registered skills (freeze-finalized when available).

        Prefers :attr:`Skill.manifest` after freeze; falls back to a provisional
        :meth:`Skill.assemble_manifest` before the app is frozen.
        """
        out: list[Manifest] = []
        for skill in self.skills():
            try:
                out.append(skill.manifest)
            except RuntimeError:
                out.append(skill.assemble_manifest())
        return tuple(out)

    def discovery_document(self) -> dict[str, Any]:
        """JSON-serializable discovery payload listing mounted skill manifests."""
        return {
            "skills": [manifest.to_dict() for manifest in self.manifests()],
        }

    def mount(
        self,
        app: App,
        *,
        discovery_path: str = DEFAULT_DISCOVERY_PATH,
    ) -> SkillRegistry:
        """Mount every registered skill via ``use_skill`` and the discovery route.

        Tool names must be unique across skills — collisions fail loud at mount
        time (aggregated ``/mcp`` has a single tool namespace). Returns ``self``.
        """
        path = _normalize_discovery_path(discovery_path)
        with self._lock:
            if self._mounted:
                msg = "SkillRegistry is already mounted"
                raise RuntimeError(msg)
            if not self._skills:
                msg = "SkillRegistry has no skills; call add() before mount()"
                raise ValueError(msg)
            skills = tuple(self._skills.values())

        _assert_unique_tool_names(skills)

        for skill in skills:
            use_skill(app, skill)

        _register_discovery_route(app, self, path)

        with self._lock:
            self._mounted = True
            self._discovery_path = path
        return self


def mount_skills(
    app: App,
    skills: SkillRegistry | Iterable[Skill],
    *,
    discovery_path: str = DEFAULT_DISCOVERY_PATH,
) -> SkillRegistry:
    """Mount skills onto ``app`` and expose a discovery endpoint.

    Accepts either a pre-built :class:`SkillRegistry` or an iterable of
    :class:`~chirp.skill.mount.Skill` instances. Each skill is mounted via
    :func:`~chirp.skill.mount.use_skill` onto the same app — Chirp's existing
    MCP surface then serves one aggregated ``/mcp`` with all tools.

    The discovery route (default ``/skills``) returns a JSON document of
    skill manifests so agents can list what the host mounts.

    Returns the :class:`SkillRegistry` (creating one when given an iterable).
    """
    if isinstance(skills, SkillRegistry):
        registry = skills
    else:
        registry = SkillRegistry()
        for skill in skills:
            registry.add(skill)
    return registry.mount(app, discovery_path=discovery_path)


def _normalize_discovery_path(path: str) -> str:
    if not isinstance(path, str) or not path.strip():
        msg = "discovery_path must be a non-empty string"
        raise ValueError(msg)
    normalized = path.strip()
    if not normalized.startswith("/"):
        normalized = "/" + normalized
    if len(normalized) > 1 and normalized.endswith("/"):
        normalized = normalized.rstrip("/")
    return normalized


def _assert_unique_tool_names(skills: tuple[Skill, ...]) -> None:
    seen: dict[str, str] = {}
    for skill in skills:
        for tool_name in skill.tools:
            owner = seen.get(tool_name)
            if owner is not None:
                msg = (
                    f"Duplicate tool name {tool_name!r} across skills "
                    f"{owner!r} and {skill.name!r}; aggregated /mcp requires "
                    "unique tool names"
                )
                raise ValueError(msg)
            seen[tool_name] = skill.name


def _register_discovery_route(
    app: App,
    registry: SkillRegistry,
    path: str,
) -> None:
    """Register GET discovery that returns the registry's manifest document."""

    @app.route(path, methods=["GET"], name="chirp_skill_discovery")
    def skill_discovery() -> Mapping[str, Any]:
        # dict → JSONResponse via negotiate (machine-facing discovery; not a
        # parallel REST resource model — mirrors Envelope / MCP wire JSON).
        return registry.discovery_document()


__all__ = [
    "DEFAULT_DISCOVERY_PATH",
    "SkillRegistry",
    "mount_skills",
]
