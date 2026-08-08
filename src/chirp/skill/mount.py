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
from chirp.tools.schema import function_to_schema

if TYPE_CHECKING:
    from chirp.app import App

_CRYPTO_INSTALL_ERROR = (
    "chirp.skill signing requires the 'cryptography' package. "
    "Install it with: pip install 'chirp[skill]'"
)


@dataclass(slots=True)
class _PendingSkillTool:
    name: str
    description: str
    handler: Callable[..., Any]
    approval_required: bool
    scopes: tuple[str, ...]


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

        @skill.tool("hook", scopes=("webhook:write",))
        def hook(payload: dict) -> dict:
            return payload

        use_skill(app, skill)
        app.register_scope("webhook:write")
    """

    __slots__ = (
        "_key_id",
        "_manifest",
        "_mounted",
        "_name",
        "_pending",
        "_private_key",
        "_provider_keys",
        "_public_key",
        "_template_sources",
        "_version",
    )

    def __init__(
        self,
        name: str,
        *,
        version: str,
        private_key: Any | None = None,
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
        if public_key is not None:
            self._public_key = public_key
        elif private_key is not None:
            self._public_key = _derive_public_key(private_key)
        else:
            # Incomplete — ``skill_contract`` ERRORs at app.check(); freeze
            # publishes an empty-key stub so contracts can inspect the skill.
            self._public_key = None
        self._provider_keys = tuple(provider_keys)
        self._pending: list[_PendingSkillTool] = []
        self._template_sources: dict[str, str] = {}
        self._mounted = False
        self._manifest: Manifest | None = None

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
    def public_key(self) -> Any | None:
        return self._public_key

    @property
    def provider_keys(self) -> tuple[str, ...]:
        return self._provider_keys

    @property
    def tools(self) -> tuple[str, ...]:
        return tuple(t.name for t in self._pending)

    @property
    def manifest(self) -> Manifest:
        """Return the freeze-finalized immutable :class:`Manifest`.

        Raises ``RuntimeError`` until ``app.freeze()`` (or ``run``/``check``)
        has published the skill domain snapshot — milo ``bindings`` precedent.
        """
        if self._manifest is None:
            msg = (
                f"Skill {self._name!r} manifest is not available until the Chirp app is frozen. "
                "Call app.freeze(), app.check(), app.run(), or serve the first request."
            )
            raise RuntimeError(msg)
        return self._manifest

    def add_template_source(self, name: str, source: str) -> None:
        """Associate a template source string with this skill for the content digest.

        Setup-only: raises after the freeze-time manifest is finalized.
        """
        if self._manifest is not None:
            msg = f"Cannot add template source {name!r} after skill {self._name!r} is frozen"
            raise RuntimeError(msg)
        if not isinstance(name, str) or not name.strip():
            msg = "Template name must be a non-empty string"
            raise ValueError(msg)
        if not isinstance(source, str):
            msg = "Template source must be a string"
            raise TypeError(msg)
        self._template_sources[name.strip()] = source

    def tool(
        self,
        name: str,
        *,
        description: str = "",
        approval_required: bool = False,
        scopes: tuple[str, ...] = (),
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """Register a skill tool whose return value is wrapped in an ``Envelope``.

        When ``scopes`` is non-empty, the wrapper calls
        :func:`~chirp.security.auth_core.enforce_auth` with
        ``AuthSpec(scopes=...)`` before the body. A 403 denial from the shared
        gate is mapped to :class:`~chirp.errors.ToolAuthError` (mutable; safe
        through tool dispatch); MCP ``tools/call`` turns that into a JSON-RPC
        error and ``authz.scope.denied`` is audited by the gate. Declare scopes
        with ``app.register_scope(...)`` so the ``auth_spec`` contract can
        validate them at startup. Passing an already-built ``Envelope`` leaves
        it unchanged.
        """
        if self._mounted:
            msg = f"Cannot register tool {name!r} after use_skill() has mounted this skill"
            raise RuntimeError(msg)
        if self._manifest is not None:
            msg = f"Cannot register tool {name!r} after skill {self._name!r} is frozen"
            raise RuntimeError(msg)
        if not isinstance(name, str) or not name.strip():
            msg = "Skill tool name must be a non-empty string"
            raise ValueError(msg)
        normalized = name.strip()
        if any(t.name == normalized for t in self._pending):
            msg = f"Duplicate skill tool name: {normalized!r}"
            raise ValueError(msg)
        scope_tuple = tuple(scopes)

        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            wrapped = _envelope_wrapper(
                func,
                skill=self._name,
                version=self._version,
                tool=normalized,
                private_key=self._private_key,
                key_id=self._key_id,
            )
            if scope_tuple:
                wrapped = _scope_gate_wrapper(wrapped, scopes=scope_tuple)
            self._pending.append(
                _PendingSkillTool(
                    name=normalized,
                    description=description,
                    handler=wrapped,
                    approval_required=approval_required,
                    scopes=scope_tuple,
                )
            )
            return wrapped

        return decorator

    def assemble_manifest(self) -> Manifest:
        """Assemble a :class:`Manifest` from this skill's current tools.

        After freeze, returns the finalized immutable manifest (same object as
        :attr:`manifest`). Before freeze, returns a provisional identity digest.
        Incomplete skills (no public key) return a stub so ``skill_contract``
        can flag them at ``app.check()``.
        """
        if self._manifest is not None:
            return self._manifest
        if self._public_key is None:
            return _incomplete_manifest(
                name=self._name,
                version=self._version,
                tools=self.tools,
                provider_keys=self._provider_keys,
            )
        return assemble_manifest(
            name=self._name,
            version=self._version,
            tools=self.tools,
            public_key=self._public_key,
            provider_keys=self._provider_keys,
        )

    def register(self, _app: App) -> None:
        """Freeze-time domain hook — finalize the immutable content-digested manifest.

        Invoked by ``AppCompiler.freeze`` via ``app.register_domain`` (milo
        ``MiloMCPAppAdapter.register`` precedent). Idempotent once published.
        Skill state is self-contained; the app argument satisfies the Domain
        protocol and is unused today.
        """
        if self._manifest is not None:
            return
        if self._public_key is None:
            self._manifest = _incomplete_manifest(
                name=self._name,
                version=self._version,
                tools=self.tools,
                provider_keys=self._provider_keys,
            )
            return
        self._manifest = assemble_manifest(
            name=self._name,
            version=self._version,
            tools=self.tools,
            public_key=self._public_key,
            provider_keys=self._provider_keys,
            tool_schemas=_skill_tool_schemas(self._pending),
            template_sources=dict(self._template_sources),
        )


def use_skill(app: App, skill: Skill) -> Skill:
    """Mount ``skill``'s tools onto ``app``'s MCP tool registry via ``app.tool``.

    Registers ``skill`` as an app domain so ``app.freeze()`` finalizes an
    immutable :class:`Manifest` with a content digest (milo
    ``register_domain`` precedent). Eagerly verifies the Ed25519 peer
    dependency when a signing key is present so missing ``cryptography`` fails
    at setup rather than on the first tool call. Registers the
    ``skill_contract`` ``app.check()`` category (chirp_ui
    ``register_contract_check`` pattern). Returns ``skill``.
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

    if skill._private_key is not None:
        _require_cryptography()

    for pending in skill._pending:
        app.tool(
            pending.name,
            description=pending.description,
            approval_required=pending.approval_required,
        )(pending.handler)

    skill._mounted = True
    app.register_domain(skill)
    _register_skill_contract(app, skill)
    return skill


def _incomplete_manifest(
    *,
    name: str,
    version: str,
    tools: tuple[str, ...],
    provider_keys: tuple[str, ...],
) -> Manifest:
    """Stub manifest for skills missing a public/signing key (contract-visible)."""
    return Manifest(
        name=name,
        version=version,
        tools=tools,
        public_key="",
        provider_keys=provider_keys,
        content_digest="",
    )


def _register_skill_contract(app: App, skill: Skill) -> None:
    """Append skill descriptors and register ``skill_contract`` once per app."""
    from chirp.contracts.rules_skill_contract import (
        SkillContractCheck,
        skill_record_from_skill,
    )

    extras = getattr(app._mutable_state, "contract_check_data", {})
    existing = list(extras.get("skills", ()))
    existing.append(skill_record_from_skill(skill))
    app.set_contract_check_data("skills", tuple(existing))
    if extras.get("_skill_contract_registered"):
        return
    app.register_contract_check(SkillContractCheck(app))
    app.set_contract_check_data("_skill_contract_registered", True)


def _skill_tool_schemas(pending: list[_PendingSkillTool]) -> dict[str, dict[str, Any]]:
    """Build the canonical tool-schema map digested into the freeze-time manifest."""
    return {
        tool.name: {
            "description": tool.description,
            "inputSchema": function_to_schema(tool.handler),
        }
        for tool in pending
    }


def _scope_gate_wrapper(
    func: Callable[..., Any],
    *,
    scopes: tuple[str, ...],
) -> Callable[..., Any]:
    """Enforce ``AuthSpec(scopes=...)`` before invoking the skill tool body.

    Decision D2 (MVP): wrap-in-decorator rather than ``ToolDef.auth``. Denial
    raises ``HTTPError(403)`` from the shared gate; the wrapper maps that to
    ``ToolAuthError`` and MCP maps it to JSON-RPC.
    """
    from chirp.pages.types import AuthSpec

    spec = AuthSpec(scopes=scopes)

    @functools.wraps(func)
    async def gated(*args: Any, **kwargs: Any) -> Any:
        from chirp._internal.invoke import invoke
        from chirp.context import get_request
        from chirp.errors import HTTPError, ToolAuthError
        from chirp.middleware.auth import get_user
        from chirp.security.auth_core import enforce_auth

        try:
            await enforce_auth(spec, get_request(), get_user())
        except HTTPError as exc:
            # Frozen HTTPError cannot carry __traceback__ through tool
            # dispatch (trace_span / contextlib). Map 401/403 to a mutable
            # ToolAuthError; MCP tools/call turns that into JSON-RPC.
            if exc.status in (401, 403):
                raise ToolAuthError(
                    status=exc.status,
                    detail=exc.detail or ("Forbidden" if exc.status == 403 else "Unauthorized"),
                ) from None
            raise
        return await invoke(func, *args, **kwargs)

    return gated


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
