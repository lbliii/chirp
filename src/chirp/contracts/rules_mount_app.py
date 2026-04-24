"""``mount_app_merge`` contract check — report sub-app entries dropped by parent-wins merge.

When ``App.mount_app`` hoists a sub-app, template globals/filters/providers/etc.
already defined on the parent win over the sub-app's registration. The
dropped sub-app entries are recorded as ``MountAppSkip`` values on the
parent's mutable state; this check surfaces them as INFO contract issues so
the user sees what was silently shadowed.

Promote to WARNING/ERROR with
``app.override_contract_severity("mount_app_merge", Severity.WARNING)``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .types import ContractIssue, Severity

if TYPE_CHECKING:
    from chirp.app.state import MountAppSkip


def check_mount_app_merge(skips: list[MountAppSkip]) -> list[ContractIssue]:
    """Emit one INFO issue per dropped sub-app registration."""
    return [
        ContractIssue(
            severity=Severity.INFO,
            category="mount_app_merge",
            message=(
                f"mount_app({skip.prefix!r}): sub-app {skip.kind} "
                f"{skip.key!r} was dropped because the parent app already "
                f"registered one. Parent wins."
            ),
        )
        for skip in skips
    ]
