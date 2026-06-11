"""Page-level htmx provisioning contract (#185).

A template can be authored with ``hx-*`` / ``sse-*`` attributes -- the whole
point of a hypermedia app -- but those attributes are inert unless the htmx
runtime is actually loaded on the page. Chirp can provision htmx in two ways:

* ``AppConfig(htmx=True)`` -- Chirp injects the htmx core ``<script>`` before
  ``</body>`` (dedup on ``data-chirp="htmx"``), or
* the layout chain ships its own htmx ``<script>`` (a ``data-chirp="htmx"``
  marker, or a ``src`` pointing at an htmx build).

When neither is true, every ``hx-*`` attribute silently does nothing: clicks
fall through to default browser navigation (or nothing), and the developer only
notices in the browser. This rule promotes that to a startup ``app.check()``
``WARNING``.

It fires once per NON-framework template that emits an ``hx-*``/``sse-*``
attribute when htmx is not provisioned. Framework templates
(``chirp/``/``chirpui/``) are skipped. Severity is ``WARNING`` and can be
promoted via ``app.override_contract_severity("htmx_provisioned",
Severity.ERROR)``.
"""

from __future__ import annotations

import re
from collections.abc import Mapping

from .types import ContractIssue, Severity

# An ``hx-*`` or ``sse-*`` attribute on an element. Matched as an attribute name
# preceded by attribute-boundary whitespace so it does not match e.g. a
# ``data-hx-target`` substring or prose. The trailing ``[=\s>/]`` requires the
# token to be a real attribute (followed by ``=value`` or end-of-tag).
# An ``hx-*`` or ``sse-*`` attribute *with a value*. Requiring ``=`` (after
# optional whitespace) means a real attribute, never a bare token in prose
# ("...about hx-get usage") or a ``data-hx-*`` substring (the leading
# negative lookbehind forbids a preceding word char or ``-``).
_HTMX_ATTR = re.compile(
    r"""(?<![\w-])(?:hx-(?:get|post|put|patch|delete|target|swap-oob|swap|trigger|boost)"""
    r"""|sse-(?:swap|connect))\s*=""",
    re.IGNORECASE,
)

# Markers proving the htmx runtime is present in *some* template in the chain:
# the Chirp dedup marker or a script src pointing at an htmx build.
_HTMX_MARKER = re.compile(
    r"""data-chirp\s*=\s*["']htmx["']|htmx\.org|/htmx@|htmx\.min\.js""",
    re.IGNORECASE,
)


def _htmx_runtime_present(template_sources: Mapping[str, str]) -> bool:
    """True when a NON-framework template carries an htmx ``<script>`` marker.

    Framework templates (``chirp/``/``chirpui/`` shell + boost layouts) always
    ship an htmx marker, but they are only rendered when the app opts into the
    chirp-ui shell. Provisioning must therefore be proven by the app's own
    layout chain, not by the bundled framework sources.
    """
    for name, source in template_sources.items():
        if name.startswith(("chirp/", "chirpui/")):
            continue
        if _HTMX_MARKER.search(source):
            return True
    return False


def check_htmx_provisioned(
    template_sources: Mapping[str, str],
    *,
    htmx_config_enabled: bool,
) -> list[ContractIssue]:
    """Flag templates emitting ``hx-*``/``sse-*`` when htmx is not provisioned.

    htmx counts as provisioned when ``htmx_config_enabled`` is ``True``
    (``AppConfig(htmx=True)``) **or** an htmx ``<script>`` marker is present in
    any scanned template source. When provisioned the rule stays silent.
    """
    if htmx_config_enabled or _htmx_runtime_present(template_sources):
        return []
    issues: list[ContractIssue] = []
    for template_name in sorted(template_sources):
        if template_name.startswith(("chirp/", "chirpui/")):
            continue
        if not _HTMX_ATTR.search(template_sources[template_name]):
            continue
        issues.append(
            ContractIssue(
                severity=Severity.WARNING,
                category="htmx_provisioned",
                message=(
                    f"Template '{template_name}' emits hx-*/sse-* attributes but "
                    "htmx is not provisioned. Set AppConfig(htmx=True) or include "
                    "an htmx <script> in the layout chain."
                ),
                template=template_name,
            )
        )
    return issues
