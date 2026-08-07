"""INFO surfacing for the MCP ``2024-11-05`` legacy-client offramp.

When an app registers tools, Chirp mounts ``/mcp`` and bridges handshake-era
clients through ``2027-07-28``. This check documents that bridge at
``app.check()`` time so operators see the migration window without a silent
break. Runtime detection and ``DeprecationWarning`` live in
``chirp.tools.handler``.
"""

from __future__ import annotations

from typing import Any

from chirp.tools.handler import (
    _LEGACY_OFFRAMP_UNTIL,
    _LEGACY_PROTOCOL_VERSION,
    _MCP_VERSION,
)

from .types import ContractIssue, Severity


def check_mcp_legacy_offramp(
    tool_registry: Any,
    *,
    mcp_path: str = "/mcp",
) -> list[ContractIssue]:
    """Emit INFO when the MCP endpoint is active and still bridges legacy clients.

    No-op when no tools are registered (``/mcp`` is not mounted). Severity is
    INFO — the bridge is intentional during the offramp; promote via
    ``app.override_contract_severity("mcp_legacy", ...)`` if desired.
    """
    if tool_registry is None or len(tool_registry) == 0:
        return []
    return [
        ContractIssue(
            severity=Severity.INFO,
            category="mcp_legacy",
            message=(
                f"MCP endpoint {mcp_path!r} bridges legacy protocol "
                f"{_LEGACY_PROTOCOL_VERSION} clients until {_LEGACY_OFFRAMP_UNTIL}. "
                f"Migrate clients to {_MCP_VERSION} with per-request params._meta "
                "and SEP-2243 routing headers."
            ),
            route=mcp_path,
            details=(
                "Legacy initialize / notifications/initialized remain accept-and-noop; "
                "requests without a modern protocol advertisement skip header "
                "enforcement. Runtime requests on the legacy path emit "
                "DeprecationWarning (see chirp.tools.handler)."
            ),
        )
    ]
