"""ChirpUI runtime contract checks."""

import re

from .types import ContractIssue, Severity

_CHIRPUI_TEMPLATE_REF_RE = re.compile(
    r"""\{%[-\s]+(?:from|extends|include|import)\s+["']chirpui/([^"']+)["']"""
)


def check_chirpui_runtime_registration(
    template_sources: dict[str, str],
    extras: dict[str, object],
) -> list[ContractIssue]:
    """Warn when app templates use ChirpUI without registering the runtime.

    Chirp's templating fallback can make ChirpUI macros render even when an app
    forgot ``use_chirp_ui(app)``. That is useful for filters, but it does not
    serve ``chirpui.css`` / ``chirpui-alpine.js`` or register ChirpUI checks.
    """
    if extras.get("chirpui_runtime_registered") is True:
        return []

    templates = sorted(
        name
        for name, source in template_sources.items()
        if not name.startswith(("chirp/", "chirpui/")) and _CHIRPUI_TEMPLATE_REF_RE.search(source)
    )
    if not templates:
        return []

    shown = ", ".join(templates[:5])
    more = f" (+{len(templates) - 5} more)" if len(templates) > 5 else ""
    return [
        ContractIssue(
            severity=Severity.WARNING,
            category="chirpui_runtime",
            message=(
                "Template imports ChirpUI components, but ChirpUI runtime registration "
                "was not detected. Call use_chirp_ui(app) to serve chirpui.css, "
                "chirpui-alpine.js, filters, and ChirpUI contract checks, or make sure "
                "you intentionally provide equivalent static/runtime integration."
            ),
            template=templates[0],
            details=f"Templates: {shown}{more}",
        )
    ]
