"""``plugin_quarantine`` contract check — report plugins skipped at mount.

When ``App.mount`` calls ``plugin.register(app, prefix)`` and that call raises,
the plugin is *quarantined* (skipped) so one broken plugin cannot abort boot.
Each quarantine is recorded as a ``PluginQuarantine`` on the app's mutable
state; this check surfaces them as ERROR contract issues — mirroring the
``MountAppSkip`` -> ``mount_app_merge`` precedent — so the operator gets a
deploy-blocking signal via ``app.check()`` / ``chirp check --deploy`` even
though boot itself stayed alive.

ERROR is the fixed default: a quarantined plugin means a half-configured app
(missing routes, middleware, hooks the plugin would have registered). Fix the
plugin's ``register()`` so it no longer raises.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .types import ContractIssue, Severity

if TYPE_CHECKING:
    from chirp.app.state import PluginQuarantine


def check_plugin_quarantine(quarantines: list[PluginQuarantine]) -> list[ContractIssue]:
    """Emit one ERROR issue per quarantined plugin."""
    return [
        ContractIssue(
            severity=Severity.ERROR,
            category="plugin_quarantine",
            message=(
                f"mount({q.prefix!r}): plugin {q.plugin_repr} was quarantined "
                f"because its register() raised: {q.error}. The app booted "
                f"without it (half-configured). Fix the plugin's register()."
            ),
        )
        for q in quarantines
    ]
