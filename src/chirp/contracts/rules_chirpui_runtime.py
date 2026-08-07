"""ChirpUI runtime contract checks."""

import re

from .types import ContractIssue, Severity

_CHIRPUI_IMPORT_RE = re.compile(r"""\{%[-\s]+from\s+["']chirpui/([^"']+)["']""")


def check_chirpui_runtime_registration(
    template_sources: dict[str, str],
    extras: dict[str, object],
) -> list[ContractIssue]:
    """Warn when app templates use ChirpUI without registering the runtime.

    Chirp no longer ambiently loads chirp-ui templates or filters from package
    presence (#860). Imports of ``chirpui/...`` without ``use_chirp_ui(app)``
    (or an equivalent explicit ``App.add_loader`` + filter registration) fail at
    render and miss CSS/Alpine/contract wiring.
    """
    if extras.get("chirpui_components") is not None:
        return []

    templates = sorted(
        name
        for name, source in template_sources.items()
        if not name.startswith(("chirp/", "chirpui/")) and _CHIRPUI_IMPORT_RE.search(source)
    )
    if not templates:
        return []

    shown = ", ".join(templates[:5])
    more = f" (+{len(templates) - 5} more)" if len(templates) > 5 else ""
    return [
        ContractIssue(
            severity=Severity.INFO,
            category="chirpui_runtime",
            message=(
                "Template imports ChirpUI components, but ChirpUI runtime registration "
                "was not detected. Call use_chirp_ui(app) to register the chirp-ui "
                "template loader, serve chirpui.css / chirpui-alpine.js, filters, and "
                "ChirpUI contract checks — package presence alone does not activate "
                "chirp-ui. Or provide an equivalent explicit App.add_loader + filter "
                "integration."
            ),
            template=templates[0],
            details=f"Templates: {shown}{more}",
        )
    ]
