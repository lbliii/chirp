"""Contract checks for runtime settings registry (#370)."""

from __future__ import annotations

from dataclasses import fields
from typing import Any

from chirp.config import AppConfig
from chirp.settings.registry import SettingSpec

from .types import ContractIssue, Severity

_BOOT_FIELD_NAMES = frozenset(f.name for f in fields(AppConfig))


def check_settings_spec(
    config: Any,
    settings_specs: tuple[SettingSpec, ...] | None = None,
) -> list[ContractIssue]:
    """Flag settings that shadow boot ``AppConfig`` fields.

    Env-aware (ERROR production / WARNING staging / silent development), matching
    ``auth_spec`` posture.
    """
    issues: list[ContractIssue] = []
    specs = settings_specs or ()
    if not specs:
        return issues

    env = getattr(config, "env", "development")
    if env not in ("production", "staging"):
        return issues
    severity = Severity.ERROR if env == "production" else Severity.WARNING

    for spec in specs:
        leaf = spec.dotted_key.split(".")[-1]
        if leaf in _BOOT_FIELD_NAMES or spec.name in _BOOT_FIELD_NAMES:
            issues.append(
                ContractIssue(
                    severity=severity,
                    category="settings_spec",
                    message=(
                        f"setting {spec.name!r} (dotted_key={spec.dotted_key!r}) shadows a "
                        "boot-time AppConfig field — runtime overrides must not collide with "
                        "frozen infra config"
                    ),
                )
            )
        if not spec.secret and leaf in {"secret_key", "password", "token", "api_key"}:
            issues.append(
                ContractIssue(
                    severity=severity,
                    category="settings_spec",
                    message=(
                        f"setting {spec.name!r} looks sensitive but secret=False — mark "
                        "secret=True so it stays env-only and is never persisted"
                    ),
                )
            )
    return issues
