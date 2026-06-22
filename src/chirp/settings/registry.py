"""Runtime-mutable app settings beside frozen ``AppConfig`` (#370).

``AppConfig`` is boot-time infra; :class:`SettingsRegistry` holds operator-mutable
values declared at setup via ``app.register_setting()``. Reads are in-memory
(no per-access I/O); persistence is a single versioned JSON document via
:class:`~chirp.settings.store.SettingsStore`.
"""

from __future__ import annotations

import os
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from chirp.settings.store import SettingsDocument, SettingsStore

SETTINGS_CHANGED_SIGNAL = "chirp.settings.changed"
_ENV_PREFIX = "CHIRP_SETTING_"


def _env_key_for(name: str) -> str:
    return _ENV_PREFIX + name.upper().replace("-", "_").replace(".", "_")


def parse_bool(raw: str) -> bool:
    return raw.strip().lower() in ("1", "true", "yes", "on")


def parse_int(raw: str) -> int:
    return int(raw.strip())


def parse_float(raw: str) -> float:
    return float(raw.strip())


def default_parser_for(value: Any) -> Callable[[str], Any]:
    if isinstance(value, bool):
        return parse_bool
    if isinstance(value, int) and not isinstance(value, bool):
        return parse_int
    if isinstance(value, float):
        return parse_float
    return str


@dataclass(frozen=True, slots=True)
class SettingSpec:
    """Declaration of one runtime-mutable setting."""

    name: str
    dotted_key: str
    default: Any
    parser: Callable[[str], Any] = str
    secret: bool = False

    def __post_init__(self) -> None:
        if not self.name or not isinstance(self.name, str):
            msg = "SettingSpec.name must be a non-empty string"
            raise ValueError(msg)
        if not self.dotted_key or not isinstance(self.dotted_key, str):
            msg = "SettingSpec.dotted_key must be a non-empty string"
            raise ValueError(msg)


@dataclass(slots=True)
class SettingsRegistry:
    """Declared settings + in-memory resolved values."""

    store: SettingsStore | None = None
    _specs: dict[str, SettingSpec] = field(default_factory=dict)
    _persisted: dict[str, Any] = field(default_factory=dict)
    _live: dict[str, Any] = field(default_factory=dict)
    _env: dict[str, Any] = field(default_factory=dict)
    _version: int = field(default=0)
    _frozen: bool = False
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def register(self, spec: SettingSpec) -> None:
        if self._frozen:
            msg = "Cannot register settings after the app has started serving requests."
            raise RuntimeError(msg)
        parser = spec.parser if spec.parser is not str else default_parser_for(spec.default)
        stored = SettingSpec(
            name=spec.name,
            dotted_key=spec.dotted_key,
            default=spec.default,
            parser=parser,
            secret=spec.secret,
        )
        with self._lock:
            if stored.name in self._specs:
                msg = f"setting {stored.name!r} is already registered"
                raise ValueError(msg)
            self._specs[stored.name] = stored

    def freeze(self) -> None:
        with self._lock:
            self._frozen = True

    @property
    def names(self) -> frozenset[str]:
        with self._lock:
            return frozenset(self._specs)

    @property
    def specs(self) -> tuple[SettingSpec, ...]:
        with self._lock:
            return tuple(self._specs.values())

    @property
    def empty(self) -> bool:
        with self._lock:
            return not self._specs

    @property
    def version(self) -> int:
        with self._lock:
            return self._version

    def spec(self, name: str) -> SettingSpec | None:
        with self._lock:
            return self._specs.get(name)

    def apply_persisted(self, doc: SettingsDocument | None) -> None:
        if doc is None:
            return
        with self._lock:
            self._version = max(self._version, int(doc.get("version", 0)))
            raw = doc.get("values", {})
            if not isinstance(raw, dict):
                return
            for name, spec in self._specs.items():
                if spec.secret:
                    continue
                if spec.dotted_key in raw:
                    self._persisted[name] = raw[spec.dotted_key]

    def apply_env(self) -> None:
        with self._lock:
            for name, spec in self._specs.items():
                env_name = _env_key_for(name)
                if env_name not in os.environ:
                    continue
                raw = os.environ[env_name]
                try:
                    parsed = spec.parser(raw)
                except Exception as exc:
                    msg = f"invalid env override {env_name}={raw!r} for setting {name!r}"
                    raise ValueError(msg) from exc
                self._env[name] = parsed

    def get(self, name: str) -> Any:
        with self._lock:
            spec = self._specs.get(name)
            if spec is None:
                msg = f"setting {name!r} is not registered"
                raise KeyError(msg)
            return self._resolved_value_locked(name, spec)

    def _resolved_value_locked(self, name: str, spec: SettingSpec) -> Any:
        if name in self._env:
            return self._env[name]
        if name in self._live:
            return self._live[name]
        if name in self._persisted:
            return self._persisted[name]
        return spec.default

    def export_document(self) -> SettingsDocument:
        with self._lock:
            values: dict[str, Any] = {}
            for name, spec in self._specs.items():
                if spec.secret:
                    continue
                values[spec.dotted_key] = self._resolved_value_locked(name, spec)
            return {"version": self._version, "values": values}

    async def set(self, name: str, value: Any) -> int:
        """Mutate *name*, persist when configured, return the new version."""
        with self._lock:
            spec = self._specs.get(name)
            if spec is None:
                msg = f"setting {name!r} is not registered"
                raise KeyError(msg)
            if spec.secret:
                msg = f"setting {name!r} is secret (env-only) and cannot be mutated at runtime"
                raise ValueError(msg)
            if name in self._env:
                msg = (
                    f"setting {name!r} is pinned by {_env_key_for(name)} and "
                    "cannot be overridden at runtime"
                )
                raise ValueError(msg)
            self._live[name] = value
            self._version += 1
            version = self._version
            store = self.store
            doc: SettingsDocument = {
                "version": self._version,
                "values": {
                    sspec.dotted_key: self._resolved_value_locked(sname, sspec)
                    for sname, sspec in self._specs.items()
                    if not sspec.secret
                },
            }

        if store is not None:
            await store.save(doc)
        return version

    def redacted_repr(self) -> dict[str, str]:
        with self._lock:
            out: dict[str, str] = {}
            for name, spec in self._specs.items():
                if spec.secret:
                    out[name] = "<redacted>"
                else:
                    out[name] = repr(self._resolved_value_locked(name, spec))
            return out
