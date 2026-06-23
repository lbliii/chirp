"""chirp-ui Alpine runtime probe — rendered HTML must wire chirpui-alpine.js (#191).

When an app calls ``use_chirp_ui(app)`` and renders interactive chirp-ui macros
(theme toggle, dialogs, dropdowns, …) but the ``chirpui-alpine.js`` registration
script is missing from the served HTML, every component is silently inert. The
pure helper ``chirp_ui.alpine.check_alpine_runtime`` detects that mismatch; this
rule probes a representative full-page GET route through the live middleware
stack (so injection is included) and surfaces problems at ``app.check()`` /
freeze-time debug checks.

Severity mirrors the #191 contract: **ERROR** when ``app.config.debug`` is
True (dev/freeze path fails loud), **WARNING** otherwise. Skipped when chirp-ui
is inactive or no app template uses a chirp-ui Alpine factory.
"""

from __future__ import annotations

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import TYPE_CHECKING, Any

from chirp.contracts.types import ContractIssue, Severity

if TYPE_CHECKING:
    from chirp.app import App
    from chirp.app.state import ContractCheckSnapshot

_LOG = logging.getLogger("chirp.contracts")


def _probe_get_paths(snapshot: ContractCheckSnapshot) -> tuple[str, ...]:
    router = snapshot.router
    if router is None:
        return ()
    paths: list[str] = []
    for route in router.routes:
        methods = route.methods or ["GET"]
        if "GET" not in methods:
            continue
        path = route.path
        if "{" in path:
            continue
        paths.append(path)
    return tuple(sorted(paths, key=lambda p: (p != "/", p)))


async def _fetch_html(app: App, path: str) -> tuple[int, str]:
    from chirp.testing import TestClient

    async with TestClient(app) as client:
        response = await client.get(path)
        text = response.text if hasattr(response, "text") else str(response.body)
        return response.status, text


def _run_probe(coro):
    """Run an async probe from sync contract checks (pytest may have a loop)."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    with ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()


def check_chirpui_alpine_runtime(
    app: App,
    snapshot: ContractCheckSnapshot,
    config: Any,
) -> list[ContractIssue]:
    """Probe rendered HTML for missing chirp-ui Alpine runtime wiring."""
    if not snapshot.extras.get("chirpui_components"):
        return []

    try:
        import chirp_ui
    except ImportError:
        return []

    check_alpine_runtime = getattr(chirp_ui, "check_alpine_runtime", None)
    if check_alpine_runtime is None:
        return []

    probe_path: str | None = None
    probe_result = None

    for path in _probe_get_paths(snapshot):
        try:
            status, html = _run_probe(_fetch_html(app, path))
        except Exception:
            _LOG.debug("chirp-ui Alpine runtime probe failed for %s", path, exc_info=True)
            continue
        if status != 200:
            continue
        runtime = check_alpine_runtime(html)
        if runtime.factories_used:
            probe_path = path
            probe_result = runtime
            break

    if probe_path is None or probe_result is None:
        return []

    if probe_result.ok and not probe_result.problems:
        return []

    severity = Severity.ERROR if bool(getattr(config, "debug", False)) else Severity.WARNING
    details_parts: list[str] = []
    if probe_result.factories_used:
        details_parts.append("factories: " + ", ".join(sorted(probe_result.factories_used)))
    if probe_result.problems:
        details_parts.extend(probe_result.problems)

    message = (
        "Rendered page uses chirp-ui Alpine factories but the runtime is not "
        "fully wired in the served HTML"
    )
    if not probe_result.ok:
        missing = ", ".join(sorted(probe_result.missing))
        message += f" (missing registration script for: {missing})"
    elif probe_result.problems:
        message += f" ({probe_result.problems[0]})"

    return [
        ContractIssue(
            severity=severity,
            category="chirpui_alpine_runtime",
            message=message,
            route=probe_path,
            details="; ".join(details_parts) if details_parts else None,
        )
    ]
