"""Shared compiled regex patterns used across contract rule modules.

Duplicate patterns were consolidated here from template_scan, rules_islands,
rules_layout, rules_accessibility, rules_swap, rules_sse, rules_form_routes,
rules_context_cascade, and rules_route_contract.

Convention: patterns used by multiple rule files live here.  Patterns used by
only one file stay in that file at module level (never inline).
"""

import re

# ---------------------------------------------------------------------------
# HTML attribute patterns
# ---------------------------------------------------------------------------

ID_ATTR = re.compile(r'\bid\s*=\s*["\']([^"\']*)["\']')
"""Extract ``id="..."`` value from an HTML tag's attributes."""

METHOD_POST = re.compile(r'method\s*=\s*["\']post["\']', re.IGNORECASE)
"""Detect ``method="post"`` on a ``<form>`` tag."""

# ---------------------------------------------------------------------------
# Template / Kida expression patterns
# ---------------------------------------------------------------------------

KIDA_EXPR = re.compile(r"\{\{.*?\}\}")
"""Match a Kida/Jinja2 ``{{ ... }}`` expression (lazy, single-line)."""

# ---------------------------------------------------------------------------
# URL / path patterns
# ---------------------------------------------------------------------------

PATH_PARAM = re.compile(r"\{(\w+)\}")
"""Extract path parameter names from route patterns like ``/users/{user_id}``."""

# ---------------------------------------------------------------------------
# SSE connect tag patterns
#
# Two variants built from the same structure.  ``SSE_CONNECT_TAG`` captures the
# URL value (used by rules_sse for route cross-referencing).
# ``SSE_CONNECT_TAG_BASIC`` omits the URL capture (used by rules_swap for
# tag-level analysis).
# ---------------------------------------------------------------------------

SSE_CONNECT_TAG = re.compile(
    r"<(?P<tag>\w+)\b(?P<attrs>[^>]*\bsse-connect\s*=\s*[\"'](?P<url>[^\"']+)[\"'][^>]*)>",
    re.IGNORECASE,
)
"""SSE connect tag with named ``url`` capture group."""

SSE_CONNECT_TAG_BASIC = re.compile(
    r"<(?P<tag>\w+)\b(?P<attrs>[^>]*\bsse-connect\s*=\s*[\"'][^\"']+[\"'][^>]*)>",
    re.IGNORECASE,
)
"""SSE connect tag without URL capture (tag + attrs only)."""
