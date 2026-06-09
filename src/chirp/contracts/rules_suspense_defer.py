"""Undiscoverable Suspense deferred-block contract.

``Suspense(...)`` defers awaitable context values: the shell renders with each
deferred key set to the ``DEFERRED`` sentinel, then every block whose
``depends_on`` references a deferred key is re-rendered and streamed as an OOB
swap. Blocks are discovered automatically via kida's ``block_metadata()``.

When a deferred key is *used* by the template (it self-declares the key via
``"<NAME>" in __chirp_defer_pending__`` or the ``<NAME> is deferred`` test) but
**no block depends on it**, auto-discovery finds nothing to re-render. At
runtime ``render_suspense`` already fails loud (``ConfigurationError`` before any
shell bytes flush), but the developer only learns when a request hits the route.
This rule promotes that failure to a startup ``app.check()`` ``WARNING`` and
recommends the ``defer_blocks=(...)`` escape hatch.

Detection is scoped to templates that **self-declare** their defer keys (the
same reliable static signal :mod:`chirp.contracts.rules_defer_falsy` uses), so
it cannot statically know which ``Suspense`` kwargs are awaitable but also never
false-positives on arbitrary ``{% if x %}`` or sync-only ``Suspense`` usage.
Templates whose route handler passes ``defer_blocks=`` bypass auto-discovery
entirely, so they are exempt. Severity is ``WARNING`` -- the rule ships
informational by default and can be promoted to ``ERROR`` via
``app.override_contract_severity("suspense_defer", Severity.ERROR)`` in CI.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import TYPE_CHECKING

from .rules_defer_falsy import _DEFER_PENDING_DECL, _DEFERRED_TEST
from .types import ContractIssue, Severity

if TYPE_CHECKING:
    from kida import Environment

# A ``defer_blocks=`` kwarg. Used by the checker to build the opt-out set of
# templates whose route handler bypasses auto-discovery (the explicit escape
# hatch). Matching is conservative: any handler source containing both a
# ``Suspense(`` call and a ``defer_blocks=`` kwarg exempts every template that
# handler references from this check.
SUSPENSE_DEFER_BLOCKS = re.compile(r"\bdefer_blocks\s*=")


def _declared_defer_keys(source: str) -> set[str]:
    """Collect keys a template self-declares as deferred.

    Mirrors ``check_defer_falsy_conditionals``: a key counts as declared when
    the template references it via ``"<NAME>" in __chirp_defer_pending__`` or
    the ``<NAME> is deferred`` test.
    """
    keys: set[str] = set()
    keys.update(_DEFER_PENDING_DECL.findall(source))
    keys.update(_DEFERRED_TEST.findall(source))
    return keys


def _discoverable_root_keys(env: Environment, template_name: str) -> set[str] | None:
    """Return the set of context-key roots any block depends on.

    Mirrors ``_find_deferred_blocks`` in ``templating/suspense.py``: a deferred
    key is auto-discoverable when some block's ``depends_on`` path has it as the
    root (``dep_path.split(".")[0]``). Returns ``None`` when the template cannot
    be loaded/analyzed so the caller skips silently rather than false-positive.
    """
    try:
        template = env.get_template(template_name)
        metadata = template.block_metadata()
    except Exception:
        return None
    roots: set[str] = set()
    for block_meta in metadata.values():
        for dep_path in getattr(block_meta, "depends_on", ()):
            roots.add(dep_path.split(".")[0])
    return roots


def check_suspense_undiscoverable(
    template_sources: Mapping[str, str],
    kida_env: Environment | None,
    *,
    defer_blocks_templates: frozenset[str] = frozenset(),
) -> list[ContractIssue]:
    """Flag Suspense templates whose declared defer keys are undiscoverable.

    Only fires when a template **explicitly** declares a key as deferred (via
    ``__chirp_defer_pending__`` membership or the ``is deferred`` test) and
    **no** block's ``depends_on`` has that key as its root. One ``WARNING`` per
    (template, key) pair.

    ``defer_blocks_templates`` lists templates whose route handler passes
    ``defer_blocks=`` to ``Suspense(...)``; those bypass auto-discovery, so they
    are exempt from the check.
    """
    if kida_env is None:
        return []
    issues: list[ContractIssue] = []
    for template_name in sorted(template_sources):
        if template_name.startswith(("chirp/", "chirpui/")):
            continue
        if template_name in defer_blocks_templates:
            continue
        declared = _declared_defer_keys(template_sources[template_name])
        if not declared:
            continue
        discoverable = _discoverable_root_keys(kida_env, template_name)
        if discoverable is None:
            continue
        issues.extend(
            ContractIssue(
                severity=Severity.WARNING,
                category="suspense_defer",
                message=(
                    f"Template '{template_name}' declares Suspense-deferred key "
                    f"'{key}' (via 'is deferred' or '__chirp_defer_pending__') but "
                    f"no block depends on '{key}', so auto-discovery finds no block "
                    "to re-render and the deferred data would never reach the DOM "
                    "(skeletons stay forever). Reference the key inside a "
                    f"'{{% block ... %}}' so block_metadata().depends_on can find it, "
                    "or pass the blocks explicitly with "
                    "Suspense(..., defer_blocks=(...)) in the route handler."
                ),
                template=template_name,
            )
            for key in sorted(declared - discoverable)
        )
    return issues
