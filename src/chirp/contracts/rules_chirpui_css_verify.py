"""ChirpUI CSS-verify contract (#157 child 2).

When chirp-ui is active (``use_chirp_ui(app)``), app templates that emit
``chirpui-*`` class tokens should resolve to classes defined in the shipped
chirp-ui stylesheet. Unknown tokens are almost always typos or stale markup
after a library upgrade — the same class of silent visual breakage that
:func:`~chirp.contracts.rules_macro_css.check_macro_css` catches when chirp-ui
is *inactive*.

This rule is the symmetric complement: it fires when chirp-ui **is** active and
a literal ``class=`` attribute references a ``chirpui-*`` token that does not
exist in the installed chirp-ui CSS partials.

Severity is ``WARNING`` by default and can be promoted via
``app.override_contract_severity("chirpui_css_verify", Severity.ERROR)``.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from functools import lru_cache

from .types import ContractIssue, Severity

_CLASS_ATTR_RE = re.compile(
    r"""class\s*=\s*(["'])(?P<value>[^"']*)\1""",
    re.IGNORECASE,
)
_CHIRPUI_CLASS_TOKEN = re.compile(r"(?<![A-Za-z0-9_-])(chirpui-[A-Za-z0-9_-]+)")
_CHIRPUI_CSS_CLASS = re.compile(r"\.(chirpui-[A-Za-z0-9_-]+)")


@lru_cache(maxsize=1)
def _known_chirpui_css_classes() -> frozenset[str] | None:
    """Return every ``chirpui-*`` class selector from the installed chirp-ui CSS."""
    try:
        from chirp_ui.css_subset import css_partial_root
    except ImportError:
        return None

    root = css_partial_root()
    if not root.is_dir():
        return None

    classes: set[str] = set()
    for path in root.glob("*.css"):
        classes.update(_CHIRPUI_CSS_CLASS.findall(path.read_text(encoding="utf-8")))
    return frozenset(classes) if classes else None


def _literal_chirpui_class_tokens(source: str) -> set[str]:
    tokens: set[str] = set()
    for match in _CLASS_ATTR_RE.finditer(source):
        tokens.update(_CHIRPUI_CLASS_TOKEN.findall(match.group("value")))
    return tokens


def check_chirpui_css_verify(
    template_sources: Mapping[str, str],
    *,
    chirpui_active: bool,
) -> list[ContractIssue]:
    """Flag unknown ``chirpui-*`` class tokens when chirp-ui CSS is active."""
    if not chirpui_active:
        return []

    known = _known_chirpui_css_classes()
    if not known:
        return []

    issues: list[ContractIssue] = []
    for template_name in sorted(template_sources):
        if template_name.startswith(("chirp/", "chirpui/")):
            continue
        unknown = sorted(_literal_chirpui_class_tokens(template_sources[template_name]) - known)
        if not unknown:
            continue
        shown = ", ".join(unknown[:5])
        more = f" (+{len(unknown) - 5} more)" if len(unknown) > 5 else ""
        issues.append(
            ContractIssue(
                severity=Severity.WARNING,
                category="chirpui_css_verify",
                message=(
                    f"Template '{template_name}' uses chirp-ui class tokens with no "
                    f"backing CSS in the installed chirp-ui package: {shown}{more}. "
                    "Check for typos or upgrade chirp-ui."
                ),
                template=template_name,
                details=f"Unknown classes: {', '.join(unknown)}",
            )
        )
    return issues
