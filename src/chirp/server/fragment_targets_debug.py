"""Debug JSON endpoint for the fragment target registry.

Serves a machine-readable view of the registry at
``/__chirp/debug/fragment-targets`` when ``debug=True``. Complements the
startup banner (``terminal_checks._format_fragment_registry``) and the
``fragment_target_orphan`` contract check — same data, JSON shape, so
scripts and devtools UIs can consume it.
"""

import json

from chirp.templating.fragment_target_registry import (
    FragmentTargetConfig,
    FragmentTargetRegistry,
)

FRAGMENT_TARGETS_DEBUG_PATH = "/__chirp/debug/fragment-targets"


def _target_payload(target_id: str, config: FragmentTargetConfig) -> dict:
    return {
        "target_id": target_id,
        "fragment_block": config.fragment_block,
        "triggers_shell_update": config.triggers_shell_update,
        "required": config.required,
        "omit_outer_layouts": config.omit_outer_layouts,
        "description": config.description,
        "scope_name": config.scope_name,
    }


def render_fragment_targets_debug(registry: FragmentTargetRegistry | None) -> str:
    """Serialize the fragment target registry to a JSON string."""
    if registry is None:
        return json.dumps({"contracts": [], "unscoped": []})

    all_ids = sorted(registry.registered_targets)
    seen_in_contract: set[str] = set()
    contracts_payload: list[dict] = []

    for contract in registry.registered_contracts:
        targets: list[dict] = []
        for target in contract.targets:
            tid = target.target_id.lstrip("#")
            config = registry.get(tid)
            if config is None:
                continue
            seen_in_contract.add(tid)
            targets.append(_target_payload(tid, config))
        contracts_payload.append(
            {
                "name": contract.name,
                "description": contract.description,
                "targets": targets,
            }
        )

    unscoped: list[dict] = []
    for tid in all_ids:
        if tid in seen_in_contract:
            continue
        config = registry.get(tid)
        if config is None:
            continue
        unscoped.append(_target_payload(tid, config))

    return json.dumps(
        {"contracts": contracts_payload, "unscoped": unscoped},
        indent=2,
    )
