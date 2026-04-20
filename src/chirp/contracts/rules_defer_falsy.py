"""Suspense ``{% if key %}`` defer-falsy footgun detection.

A deferred Suspense key is ``None`` in the shell render, then resolves to
real data. Templates that branch on raw truthiness (``{% if key %}``) treat
empty list ``[]``, empty string ``""``, ``0`` and ``False`` *identically* to
the loading state — the skeleton renders forever and a user sees a
perpetual spinner with no console error.

CLAUDE.md and AGENTS.md document the fix (``{% if key is not none %}`` or
``"key" in __chirp_defer_pending__``); this rule promotes the docs to a
startup-time contract check.

Detection is scoped to templates that **self-declare** their defer keys via
``"<NAME>" in __chirp_defer_pending__`` or the ``<NAME> is deferred`` test,
so we don't false-positive on arbitrary ``{% if x %}`` elsewhere in the
codebase. Severity is ``WARNING`` — the rule ships informational by default
and can be promoted to ``ERROR`` via
``app.override_contract_severity("defer_falsy", Severity.ERROR)`` in CI.
"""

import re

from .types import ContractIssue, Severity

# A template self-declares a key as deferred via membership in
# __chirp_defer_pending__: e.g. {% if "stats" in __chirp_defer_pending__ %}.
_DEFER_PENDING_DECL = re.compile(
    r"""['"]([A-Za-z_][A-Za-z0-9_]*)['"]\s+in\s+__chirp_defer_pending__""",
)

# Or via Chirp's kida `deferred` test: e.g. {% if stats is deferred %}.
_DEFERRED_TEST = re.compile(
    r"""\b([A-Za-z_][A-Za-z0-9_]*)\s+is\s+(?:not\s+)?deferred\b""",
)


def _bare_truthy_pattern(key: str) -> re.Pattern[str]:
    r"""Build a regex that matches ``{% if KEY %}`` / ``{% if not KEY %}``.

    Matches kida ``if`` and ``elif`` start tags with optional whitespace
    trimming (``{%-``, ``-%}``) and an optional ``not``. Crucially, the
    pattern requires the tag to *end* immediately after the identifier
    (``\s*-?%}``) — that's what excludes ``{% if KEY is none %}``,
    ``{% if KEY == X %}``, ``{% if KEY and Y %}``, etc.
    """
    return re.compile(
        r"\{%-?\s*(?:el)?if\s+(?:not\s+)?" + re.escape(key) + r"\s*-?%\}",
    )


def check_defer_falsy_conditionals(template_sources: dict[str, str]) -> list[ContractIssue]:
    """Flag bare ``{% if KEY %}`` conditionals on Suspense-deferred keys.

    Only fires when ``KEY`` is **explicitly** declared as a defer key in the
    same template (via ``__chirp_defer_pending__`` membership or the
    ``is deferred`` test). One ``WARNING`` per (template, key) pair.
    """
    issues: list[ContractIssue] = []
    for template_name, source in template_sources.items():
        defer_keys: set[str] = set()
        defer_keys.update(_DEFER_PENDING_DECL.findall(source))
        defer_keys.update(_DEFERRED_TEST.findall(source))
        if not defer_keys:
            continue
        for key in sorted(defer_keys):
            if not _bare_truthy_pattern(key).search(source):
                continue
            issues.append(
                ContractIssue(
                    severity=Severity.WARNING,
                    category="defer_falsy",
                    message=(
                        f"Template '{template_name}' branches on '{{% if {key} %}}' "
                        f"(or '{{% if not {key} %}}') for Suspense-deferred key "
                        f"'{key}'. After resolution, falsy values like [], '', 0, "
                        "False are indistinguishable from the loading state, so the "
                        "skeleton/fallback branch renders forever and the user sees "
                        "a perpetual spinner with no console error. Use "
                        f"'{{% if {key} is not none %}}' or "
                        f"'{{% if \"{key}\" in __chirp_defer_pending__ %}}' / "
                        f"'{{% if {key} is deferred %}}' to distinguish loading "
                        "from loaded."
                    ),
                    template=template_name,
                )
            )
    return issues
