"""Env-var keystore + presence-only ``key-status`` tool for Orrery hosts.

Operator keys are declared by *name* on skill manifests (``provider_keys``).
Values live in the process environment and are resolved by name for
server-side skill handlers. Agents see only a presence report — never
secret values — via the host-level ``key-status`` MCP tool.

BYO-key-per-invocation is explicitly out of scope (sibling Not-now).
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from chirp.app import App

KEY_STATUS_TOOL = "key-status"

_STATUS_DOC_KEYS = frozenset({"keys"})
_STATUS_ENTRY_KEYS = frozenset({"name", "present"})


class SecretLeakError(ValueError):
    """Raised when a secret value would be exposed in agent-visible output."""


@dataclass(frozen=True, slots=True)
class KeyStatus:
    """Presence-only report for one provider key name.

    Never carries the secret value — only whether the env var is set and
    non-empty.
    """

    name: str
    present: bool

    def to_dict(self) -> dict[str, Any]:
        """JSON-serializable presence record (no ``value`` field)."""
        return {"name": self.name, "present": self.present}


class EnvKeystore:
    """Resolve provider keys from environment variables by name.

    Pass a mapping for tests; omit to read :data:`os.environ` live at each
    call (operator can set keys without restarting in some deployments).

    Server-side handlers may call :meth:`resolve` / :meth:`get`. Agent-facing
    surfaces must use :meth:`status` / :meth:`status_document` only.
    """

    __slots__ = ("_environ",)

    def __init__(self, environ: Mapping[str, str] | None = None) -> None:
        self._environ: Mapping[str, str] | None = environ

    def __repr__(self) -> str:
        source = "custom" if self._environ is not None else "os.environ"
        return f"EnvKeystore(environ={source})"

    def _env(self) -> Mapping[str, str]:
        return self._environ if self._environ is not None else os.environ

    def _lookup(self, name: str) -> str | None:
        _require_key_name(name)
        value = self._env().get(name)
        if value is None or value == "":
            return None
        return value

    def get(self, name: str) -> str | None:
        """Return the secret for *server-side* use, or ``None`` if unset/empty.

        Never pass the return value into Envelope payloads, MCP tool
        responses, discovery documents, or logs.
        """
        return self._lookup(name)

    def resolve(self, name: str) -> str:
        """Return the secret for *server-side* use; raise ``KeyError`` if absent.

        Never pass the return value into Envelope payloads, MCP tool
        responses, discovery documents, or logs.
        """
        value = self._lookup(name)
        if value is None:
            msg = f"Provider key {name!r} is not set in the environment"
            raise KeyError(msg)
        return value

    def present(self, name: str) -> bool:
        """True when the named env var is set and non-empty."""
        return self._lookup(name) is not None

    def status(self, names: Iterable[str]) -> tuple[KeyStatus, ...]:
        """Presence-only report for ``names`` (deduped, order-preserving)."""
        ordered = _normalize_names(names)
        return tuple(KeyStatus(name=n, present=self.present(n)) for n in ordered)

    def status_document(self, names: Iterable[str]) -> dict[str, Any]:
        """JSON-safe presence document for the ``key-status`` tool.

        Shape::

            {"keys": [{"name": "OPENWEATHER_API_KEY", "present": true}, ...]}
        """
        return {"keys": [entry.to_dict() for entry in self.status(names)]}

    def as_key_status_fn(self) -> Callable[[str, tuple[str, ...]], Mapping[str, bool | None]]:
        """Adapter for :func:`~chirp.skill.console.mount_console` ``key_status``.

        Returns a callable ``(skill_name, provider_key_names) -> {name: present}``
        that reports presence only — never secret values. ``skill_name`` is
        accepted for signature compatibility and ignored (env keys are global).
        """

        def _key_status(
            _skill_name: str,
            provider_key_names: tuple[str, ...],
        ) -> dict[str, bool | None]:
            return {name: self.present(name) for name in provider_key_names}

        return _key_status


def assert_no_secret_leak(document: Any, *, secrets: Iterable[str]) -> None:
    """Fail loud if any non-empty secret value appears in ``document``.

    Serializes ``document`` to canonical JSON and scans for each secret as a
    contiguous substring. Empty secrets are skipped. Used by the
    ``key-status`` tool before returning, and available to hosts that assemble
    other agent-visible payloads from keystore-backed data.
    """
    material = tuple(s for s in secrets if isinstance(s, str) and s)
    if not material:
        return
    blob = json.dumps(
        document,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    )
    for secret in material:
        if secret in blob:
            msg = (
                "Secret value would leak into agent-visible output; "
                "refuse to emit keystore-backed payload"
            )
            raise SecretLeakError(msg)


def register_key_status_tool(
    app: App,
    keystore: EnvKeystore,
    *,
    names: Iterable[str],
    tool_name: str = KEY_STATUS_TOOL,
) -> str:
    """Register the host-level ``key-status`` MCP tool (presence only).

    The tool returns :meth:`EnvKeystore.status_document` for the declared
    key names and runs :func:`assert_no_secret_leak` before returning so
    resolved secret values never enter the MCP response (or Envelope path —
    this is a plain ``app.tool``, not a skill Envelope wrapper).

    Returns the registered tool name.
    """
    if not isinstance(keystore, EnvKeystore):
        msg = "register_key_status_tool() requires an EnvKeystore"
        raise TypeError(msg)
    if not isinstance(tool_name, str) or not tool_name.strip():
        msg = "tool_name must be a non-empty string"
        raise ValueError(msg)
    normalized_tool = tool_name.strip()
    ordered = _normalize_names(names)

    @app.tool(
        normalized_tool,
        description=(
            "Report whether declared provider keys are set "
            "(presence only; never returns secret values)."
        ),
    )
    def key_status() -> dict[str, Any]:
        document = keystore.status_document(ordered)
        _assert_status_document_shape(document)
        held = tuple(v for name in ordered if (v := keystore.get(name)) is not None)
        assert_no_secret_leak(document, secrets=held)
        return document

    return normalized_tool


def _assert_status_document_shape(document: Any) -> None:
    """Structural leak guard — status docs may only carry name + present."""
    if not isinstance(document, dict):
        msg = "key-status document must be a dict"
        raise SecretLeakError(msg)
    if set(document.keys()) != _STATUS_DOC_KEYS:
        msg = "key-status document keys must be exactly {'keys'}"
        raise SecretLeakError(msg)
    entries = document["keys"]
    if not isinstance(entries, list):
        msg = "key-status 'keys' must be a list"
        raise SecretLeakError(msg)
    for entry in entries:
        if not isinstance(entry, dict):
            msg = "key-status entry must be a dict"
            raise SecretLeakError(msg)
        if set(entry.keys()) != _STATUS_ENTRY_KEYS:
            msg = "key-status entry keys must be exactly {'name', 'present'}"
            raise SecretLeakError(msg)
        if not isinstance(entry["name"], str):
            msg = "key-status entry 'name' must be a str"
            raise SecretLeakError(msg)
        if not isinstance(entry["present"], bool):
            msg = "key-status entry 'present' must be a bool"
            raise SecretLeakError(msg)


def _require_key_name(name: str) -> None:
    if not isinstance(name, str) or not name.strip():
        msg = "Provider key name must be a non-empty string"
        raise ValueError(msg)
    if name != name.strip():
        msg = f"Provider key name must not have leading/trailing whitespace: {name!r}"
        raise ValueError(msg)


def _normalize_names(names: Iterable[str]) -> tuple[str, ...]:
    ordered: list[str] = []
    seen: set[str] = set()
    for raw in names:
        _require_key_name(raw)
        if raw in seen:
            continue
        seen.add(raw)
        ordered.append(raw)
    return tuple(ordered)


__all__ = [
    "KEY_STATUS_TOOL",
    "EnvKeystore",
    "KeyStatus",
    "SecretLeakError",
    "assert_no_secret_leak",
    "register_key_status_tool",
]
