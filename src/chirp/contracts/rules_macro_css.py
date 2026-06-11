"""Dangling-macro-CSS contract (#148 child 1).

Chirp's core macro library (``chirp/alpine.html``, ``chirp/forms.html``) emits
elements decorated with class names such as ``chirp-dropdown``, ``chirp-modal``,
``chirp-tabs``, and ``field--error``. Those classes carry **no backing
stylesheet on their own** -- the styles ship with chirp-ui. An app that imports
the core macros (or hand-rolls markup using those class names) **without**
activating chirp-ui gets unstyled, broken-looking components with no error.

This rule promotes that silent visual breakage to a startup ``app.check()``
``WARNING``. It fires when a NON-framework template either

* imports a macro from ``chirp/alpine.html`` or ``chirp/forms.html``, or
* literally emits one of the dangling class names,

**and** chirp-ui is not active (``use_chirp_ui(app)`` was never called, so the
``chirpui_components`` snapshot signal is falsy). Framework templates
(``chirp/``/``chirpui/``) are skipped so the macro source files do not
self-trigger.

Severity is ``WARNING`` -- the rule ships informational by default and can be
promoted via ``app.override_contract_severity("macro_css", Severity.ERROR)``.
"""

from __future__ import annotations

import re
from collections.abc import Mapping

from .types import ContractIssue, Severity

# A core-macro import: ``{% from "chirp/alpine.html" import dropdown %}`` (or
# forms.html). Matches the leading ``{%-``/``{%`` plus optional whitespace, the
# ``from`` keyword, and the quoted core-macro path. Mirrors chirp-ui's import
# regex precedent in ``chirp.ext.chirp_ui``.
_CORE_MACRO_IMPORT = re.compile(
    r"""\{%[-\s]+from\s+["']chirp/(?:alpine|forms)\.html["']""",
)

# The dangling class names emitted by the core macros that have no backing CSS
# without chirp-ui.
_DANGLING_CLASSES: tuple[str, ...] = (
    "chirp-dropdown",
    "chirp-dropdown-trigger",
    "chirp-dropdown-panel",
    "chirp-modal",
    "chirp-modal-backdrop",
    "chirp-modal-content",
    "chirp-tabs",
    "chirp-tab",
    "field--error",
    "field-error",
)

# Match each class as a whole class-list token: flanked by a non-class-char (or
# string edge). Class chars are ``[A-Za-z0-9_-]``; forbidding a trailing
# ``[A-Za-z0-9_-]`` keeps ``chirp-dropdown`` from matching an app's own
# ``chirp-dropdown-zone``. Longest alternations are listed first so the engine
# prefers e.g. ``field--error`` over the ``field-error`` prefix overlap.
_DANGLING_RE = re.compile(
    r"(?<![A-Za-z0-9_-])(?:"
    + "|".join(re.escape(c) for c in sorted(_DANGLING_CLASSES, key=len, reverse=True))
    + r")(?![A-Za-z0-9_-])",
)


def check_macro_css(
    template_sources: Mapping[str, str],
    *,
    chirpui_active: bool,
) -> list[ContractIssue]:
    """Flag templates using core chirp macros/classes with no backing CSS.

    Fires one ``WARNING`` per offending non-framework template when chirp-ui is
    not active. When ``chirpui_active`` is ``True`` the backing stylesheet is
    present, so the rule stays silent regardless of macro/class usage.
    """
    if chirpui_active:
        return []
    issues: list[ContractIssue] = []
    for template_name in sorted(template_sources):
        if template_name.startswith(("chirp/", "chirpui/")):
            continue
        source = template_sources[template_name]
        if not (_CORE_MACRO_IMPORT.search(source) or _DANGLING_RE.search(source)):
            continue
        issues.append(
            ContractIssue(
                severity=Severity.WARNING,
                category="macro_css",
                message=(
                    f"Template '{template_name}' uses core chirp macros that emit "
                    "unstyled classes (e.g. chirp-dropdown, field--error) with no "
                    "backing stylesheet. Activate chirp-ui (use_chirp_ui(app)) or "
                    "ship your own CSS for these classes."
                ),
                template=template_name,
            )
        )
    return issues
