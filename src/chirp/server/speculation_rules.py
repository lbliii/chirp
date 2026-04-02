"""Speculation Rules injection — automatic prefetch/prerender hints from route definitions.

Three modes controlled by ``AppConfig.speculation_rules``:

- ``False`` / ``"off"`` — inject nothing (default).
- ``True`` / ``"conservative"`` — prefetch linked pages on hover/pointerdown.
  Safe for all apps.
- ``"moderate"`` — prefetch all static GET routes eagerly, prerender on hover.
- ``"eager"`` — prerender static GET routes eagerly.  Use only when routes
  are side-effect-free and fast.

Injected into full-page HTML responses via ``HTMLInject`` middleware,
before ``</head>``.

Chirp generates rules from the router at freeze time:

- **Static GET routes** (no path parameters) become ``"source": "list"``
  candidates.
- **Parametric routes** are expressed as ``href_matches`` patterns.
- SSE endpoints (``referenced=True``) and non-GET routes are excluded.
"""

from __future__ import annotations

import json
import re

SpeculationRulesMode = str  # "off" | "conservative" | "moderate" | "eager"


def normalize_speculation_rules(value: bool | str) -> SpeculationRulesMode:
    """Canonicalize the ``speculation_rules`` config value.

    Returns one of ``"off"``, ``"conservative"``, ``"moderate"``, or ``"eager"``.
    """
    if value is False or value == "off":
        return "off"
    if value is True or value == "conservative":
        return "conservative"
    if value == "moderate":
        return "moderate"
    if value == "eager":
        return "eager"
    msg = (
        f"Invalid speculation_rules value: {value!r}. "
        "Use False, True, 'off', 'conservative', 'moderate', or 'eager'."
    )
    raise ValueError(msg)


def _route_to_href_pattern(path: str) -> str:
    """Convert a Chirp route path to a Speculation Rules ``href_matches`` pattern.

    ``/users/{id:int}`` becomes ``/users/*``.
    """
    return re.sub(r"\{[^}]+\}", "*", path)


def build_speculation_rules_json(router: object, mode: SpeculationRulesMode) -> str:
    """Generate Speculation Rules JSON from the router.

    Returns empty string for ``"off"`` mode or when no eligible routes exist.
    """
    if mode == "off":
        return ""

    routes = getattr(router, "routes", [])

    static_urls: list[str] = []
    parametric_patterns: list[str] = []

    for route in routes:
        if "GET" not in route.methods:
            continue
        if getattr(route, "referenced", False):
            continue
        path = route.path
        if "{" in path:
            parametric_patterns.append(_route_to_href_pattern(path))
        else:
            static_urls.append(path)

    rules: dict[str, list[dict]] = {"prefetch": [], "prerender": []}
    sorted_urls = sorted(static_urls) if static_urls else []
    sorted_patterns = sorted(parametric_patterns) if parametric_patterns else []

    if mode == "conservative":
        if sorted_urls:
            rules["prefetch"].append(
                {"source": "list", "urls": sorted_urls, "eagerness": "moderate"}
            )
        if sorted_patterns:
            rules["prefetch"].append(
                {
                    "source": "document",
                    "where": {"or": [{"href_matches": p} for p in sorted_patterns]},
                    "eagerness": "conservative",
                }
            )
    elif mode == "moderate":
        if sorted_urls:
            rules["prefetch"].append({"source": "list", "urls": sorted_urls, "eagerness": "eager"})
            rules["prerender"].append(
                {"source": "list", "urls": sorted_urls, "eagerness": "moderate"}
            )
        if sorted_patterns:
            rules["prefetch"].append(
                {
                    "source": "document",
                    "where": {"or": [{"href_matches": p} for p in sorted_patterns]},
                    "eagerness": "moderate",
                }
            )
    elif mode == "eager":
        if sorted_urls:
            rules["prerender"].append({"source": "list", "urls": sorted_urls, "eagerness": "eager"})
        if sorted_patterns:
            rules["prerender"].append(
                {
                    "source": "document",
                    "where": {"or": [{"href_matches": p} for p in sorted_patterns]},
                    "eagerness": "moderate",
                }
            )

    rules = {k: v for k, v in rules.items() if v}

    if not rules:
        return ""

    return json.dumps(rules, separators=(",", ":"))


def build_speculation_rules_snippet(router: object, mode: SpeculationRulesMode) -> str:
    """Build the full ``<script type="speculationrules">`` snippet.

    Returns empty string when mode is ``"off"`` or no rules are generated.
    """
    rules_json = build_speculation_rules_json(router, mode)
    if not rules_json:
        return ""
    safe_json = rules_json.replace("<", "\\u003c").replace("&", "\\u0026")
    return f'<script type="speculationrules" data-chirp="speculation-rules">{safe_json}</script>'
