"""Skill authoring — ``Skill.tool`` + ``use_skill`` mount onto an app MCP registry.

Peer dependencies (``cryptography`` for envelope signing) are imported lazily
inside call paths (milo pattern), so ``import chirp.skill`` stays light.
"""

from __future__ import annotations

import functools
import hashlib
import inspect
import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from chirp.skill.envelope import Envelope, sign_envelope
from chirp.skill.manifest import Manifest, assemble_manifest

if TYPE_CHECKING:
    from chirp.app import App

_CRYPTO_INSTALL_ERROR = (
    "chirp.skill signing requires the 'cryptography' package. "
    "Install it (e.g. `pip install cryptography`) and retry."
)


@dataclass(slots=True)
class _PendingSkillTool:
    name: str
    description: str
    handler: Callable[..., Any]
    approval_required: bool


class Skill:
    """A named, versioned skill whose tools return signed :class:`Envelope` values.

    Decorate handlers with :meth:`tool`, then mount with :func:`use_skill`::

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

        use_skill(app, skill)
    """

    __slots__ = (
        "_key_id",
        "_mounted",
        "_name",
        "_pending",
        "_private_key",
        "_provider_keys",
        "_public_key",
        "_version",
    )

    def __init__(
        self,
        name: str,
        *,
        version: str,
        private_key: Any,
        key_id: str,
        public_key: Any | None = None,
        provider_keys: tuple[str, ...] = (),
    ) -> None:
        if not isinstance(name, str) or not name.strip():
            msg = "Skill name must be a non-empty string"
            raise ValueError(msg)
        if not isinstance(version, str) or not version.strip():
            msg = "Skill version must be a non-empty semver string"
            raise ValueError(msg)
        if not isinstance(key_id, str) or not key_id.strip():
            msg = "Skill key_id must be a non-empty string"
            raise ValueError(msg)

        self._name = name.strip()
        self._version = version.strip()
        self._private_key = private_key
        self._key_id = key_id.strip()
        self._public_key = public_key if public_key is not None else _derive_public_key(private_key)
        self._provider_keys = tuple(provider_keys)
        self._pending: list[_PendingSkillTool] = []
        self._mounted = False

    @property
    def name(self) -> str:
        return self._name

    @property
    def version(self) -> str:
        return self._version

    @property
    def key_id(self) -> str:
        return self._key_id

    @property
    def public_key(self) -> Any:
        return self._public_key

    @property
    def provider_keys(self) -> tuple[str, ...]:
        return self._provider_keys

    @property
    def tools(self) -> tuple[str, ...]:
        return tuple(t.name for t in self._pending)

    def tool(
        self,
        name: str,
        *,
        description: str = "",
        approval_required: bool = False,
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """Register a skill tool whose return value is wrapped in an ``Envelope``.

        Mirrors ``app.tool``; scope gating is a sibling (#971) and is not applied
        here. Passing an already-built ``Envelope`` leaves it unchanged.
        """
        if self._mounted:
            msg = f"Cannot register tool {name!r} after use_skill() has mounted this skill"
            raise RuntimeError(msg)
        if not isinstance(name, str) or not name.strip():
            msg = "Skill tool name must be a non-empty string"
            raise ValueError(msg)
        normalized = name.strip()
        if any(t.name == normalized for t in self._pending):
            msg = f"Duplicate skill tool name: {normalized!r}"
            raise ValueError(msg)

        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            wrapped = _envelope_wrapper(
                func,
                skill=self._name,
                version=self._version,
                tool=normalized,
                private_key=self._private_key,
                key_id=self._key_id,
            )
            self._pending.append(
                _PendingSkillTool(
                    name=normalized,
                    description=description,
                    handler=wrapped,
                    approval_required=approval_required,
                )
            )
            return wrapped

        return decorator

    def assemble_manifest(self) -> Manifest:
        """Assemble a serializable :class:`Manifest` from this skill's current tools."""
        return assemble_manifest(
            name=self._name,
            version=self._version,
            tools=self.tools,
            public_key=self._public_key,
            provider_keys=self._provider_keys,
        )


def use_skill(app: App, skill: Skill) -> Skill:
    """Mount ``skill``'s tools onto ``app``'s MCP tool registry via ``app.tool``.

    Eagerly verifies the Ed25519 peer dependency so missing ``cryptography``
    fails at setup rather than on the first tool call. Returns ``skill``.
    """
    if not isinstance(skill, Skill):
        msg = "use_skill() requires a chirp.skill.Skill instance"
        raise TypeError(msg)
    if skill._mounted:
        msg = f"Skill {skill.name!r} is already mounted"
        raise RuntimeError(msg)
    if not skill._pending:
        msg = f"Skill {skill.name!r} has no tools; decorate handlers with @skill.tool before use_skill()"
        raise ValueError(msg)

    _require_cryptography()

    for pending in skill._pending:
        app.tool(
            pending.name,
            description=pending.description,
            approval_required=pending.approval_required,
        )(pending.handler)

    skill._mounted = True
    return skill


def _envelope_wrapper(
    func: Callable[..., Any],
    *,
    skill: str,
    version: str,
    tool: str,
    private_key: Any,
    key_id: str,
) -> Callable[..., Any]:
    """Wrap ``func`` so its result is an :class:`Envelope` (unless already one)."""

    if inspect.iscoroutinefunction(func):

        @functools.wraps(func)
        async def async_wrapped(*args: Any, **kwargs: Any) -> Envelope:
            result = await func(*args, **kwargs)
            return _ensure_envelope(
                result,
                skill=skill,
                version=version,
                tool=tool,
                private_key=private_key,
                key_id=key_id,
                arguments=_call_arguments(func, args, kwargs),
            )

        return async_wrapped

    @functools.wraps(func)
    def sync_wrapped(*args: Any, **kwargs: Any) -> Envelope:
        result = func(*args, **kwargs)
        return _ensure_envelope(
            result,
            skill=skill,
            version=version,
            tool=tool,
            private_key=private_key,
            key_id=key_id,
            arguments=_call_arguments(func, args, kwargs),
        )

    return sync_wrapped


def _ensure_envelope(
    result: Any,
    *,
    skill: str,
    version: str,
    tool: str,
    private_key: Any,
    key_id: str,
    arguments: dict[str, Any],
) -> Envelope:
    if isinstance(result, Envelope):
        return result
    return sign_envelope(
        payload=result,
        skill=skill,
        version=version,
        tool=tool,
        input_digest=_input_digest(arguments),
        private_key=private_key,
        key_id=key_id,
    )


def _call_arguments(
    func: Callable[..., Any],
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
) -> dict[str, Any]:
    """Bind call args to parameter names for a stable input digest."""
    try:
        bound = inspect.signature(func).bind_partial(*args, **kwargs)
        bound.apply_defaults()
        return dict(bound.arguments)
    except TypeError, ValueError:
        return dict(kwargs)


def _input_digest(arguments: dict[str, Any]) -> str:
    canonical = json.dumps(
        arguments,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    )
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _require_cryptography() -> Any:
    try:
        from cryptography.hazmat.primitives.asymmetric import ed25519
    except ImportError as exc:
        raise ImportError(_CRYPTO_INSTALL_ERROR) from exc
    return ed25519


def _derive_public_key(private_key: Any) -> Any:
    ed25519 = _require_cryptography()
    if isinstance(private_key, ed25519.Ed25519PrivateKey):
        return private_key.public_key()
    if isinstance(private_key, bytes | bytearray):
        return ed25519.Ed25519PrivateKey.from_private_bytes(bytes(private_key)).public_key()
    msg = "private_key must be Ed25519PrivateKey or 32 raw private-key bytes"
    raise TypeError(msg)


__all__ = [
    "Skill",
    "use_skill",
]
