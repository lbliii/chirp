"""Live-block contract checks.

Validates each ``@app.live_block(route, block)`` declaration:

- ``live_block_unreachable_route`` — the declared route is not registered.
- ``live_block_unknown`` — the route's template has no block with that name.

Template is resolved via ``route_templates`` (populated by filesystem page
mounting). Imperative routes without tracked templates skip block-level
validation; the route-existence check still runs.
"""

from __future__ import annotations

import inspect
import re
from typing import TYPE_CHECKING

from .types import ContractIssue, Severity

if TYPE_CHECKING:
    from kida import Environment

    from chirp.live_blocks import LiveBlockSpec
    from chirp.routing.router import Router


_TEMPLATE_CALL_PATTERN = re.compile(
    r'(?:Template|Fragment|Page|Suspense|LayoutPage)\s*\(\s*["\']([^"\']+\.html)["\']'
)


def _resolve_template_for_route(
    route: str,
    spec: LiveBlockSpec,
    route_templates: dict[str, str],
) -> str | None:
    template = route_templates.get(route)
    if template:
        return template
    try:
        src = inspect.getsource(spec.handler)
    except TypeError, OSError:
        return None
    match = _TEMPLATE_CALL_PATTERN.search(src)
    return match.group(1) if match else None


def check_live_blocks(
    live_blocks: dict[tuple[str, str], LiveBlockSpec],
    router: Router,
    route_templates: dict[str, str],
    kida_env: Environment | None,
) -> list[ContractIssue]:
    """Validate live-block declarations against routes and templates."""
    issues: list[ContractIssue] = []
    if not live_blocks:
        return issues

    registered_paths = {getattr(r, "path", "") for r in getattr(router, "routes", [])}

    for (route, block), spec in live_blocks.items():
        if route not in registered_paths:
            issues.append(
                ContractIssue(
                    severity=Severity.ERROR,
                    category="live_block_unreachable_route",
                    message=(
                        f"@app.live_block('{route}', '{block}') targets route "
                        f"'{route}' but no such route is registered."
                    ),
                    route=route,
                )
            )
            continue

        if kida_env is None:
            continue

        template = _resolve_template_for_route(route, spec, route_templates)
        if template is None:
            continue

        try:
            tmpl = kida_env.get_template(template)
            blocks = tmpl.block_metadata()
        except Exception:
            issues.append(
                ContractIssue(
                    severity=Severity.ERROR,
                    category="live_block_unknown",
                    message=(
                        f"@app.live_block('{route}', '{block}') references template "
                        f"'{template}' which could not be loaded."
                    ),
                    route=route,
                    template=template,
                )
            )
            continue

        if block not in blocks:
            issues.append(
                ContractIssue(
                    severity=Severity.ERROR,
                    category="live_block_unknown",
                    message=(
                        f"@app.live_block('{route}', '{block}') declares block "
                        f"'{block}' but template '{template}' has no such block. "
                        f"Available: {', '.join(sorted(blocks)) or '(none)'}."
                    ),
                    route=route,
                    template=template,
                )
            )
    return issues
