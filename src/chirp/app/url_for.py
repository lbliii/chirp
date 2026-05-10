"""URL reversal for named routes.

Builds a ``{name: Route}`` index at freeze time and turns names back into
path strings at call time. Used by ``app.url_for`` and the ``{{ url_for(...) }}``
template global.

Design notes live in ``docs/rfcs/004-url-for.md``.
"""

from __future__ import annotations

import re
from types import MappingProxyType
from typing import TYPE_CHECKING, Any
from urllib.parse import quote, urlencode

from chirp.routing.params import CONVERTERS
from chirp.routing.router import parse_path

if TYPE_CHECKING:
    from collections.abc import Mapping

    from chirp.routing.route import Route


def build_routes_by_name(
    routes: list[Route],
) -> tuple[Mapping[str, Route], dict[str, list[Route]]]:
    """Return ``(by_name, collisions)`` split from a list of routes.

    ``by_name`` holds the first occurrence of each name (a stable read model
    exposed via ``MappingProxyType``). Routes that share both ``name`` and
    ``path`` are HTTP method variants of the same URL (e.g. ``GET`` from
    ``page.py`` plus ``POST`` from ``_actions.py``) and are *not* collisions
    — ``url_for`` returns the same URL either way.

    ``collisions`` maps any name claimed by routes at *different* paths to
    every conflicting ``Route`` — surfaced as a ``route_names`` contract
    issue.
    """
    by_name: dict[str, Route] = {}
    collisions: dict[str, list[Route]] = {}
    for route in routes:
        if route.name is None:
            continue
        existing = by_name.get(route.name)
        if existing is None:
            by_name[route.name] = route
        elif existing.path != route.path:
            collisions.setdefault(route.name, [existing]).append(route)
    return MappingProxyType(by_name), collisions


def resolve_url(
    routes_by_name: Mapping[str, Route],
    name: str,
    /,
    **params: Any,
) -> str:
    """Reverse a named route to a URL path.

    Path-param kwargs substitute into ``{braces}`` and are percent-encoded;
    any remaining kwargs become a urlencoded query string. ``None`` values
    in the query are skipped (Starlette convention).

    Raises:
        LookupError: ``name`` is not registered. The message lists every
            known name so the caller can correct a typo.
        KeyError: A required path param was not supplied.
        TypeError: A path-param value is a list (path segments must be scalar).
    """
    route = routes_by_name.get(name)
    if route is None:
        known = sorted(routes_by_name)
        msg = f"No route named {name!r}. Known names: {known}"
        raise LookupError(msg)

    segments = parse_path(route.path)
    path_param_names = {s.param_name for s in segments if s.is_param and s.param_name}
    used: set[str] = set()
    rendered: list[str] = []
    for seg in segments:
        if seg.is_param:
            param_name = seg.param_name or ""
            if param_name not in params:
                missing = sorted(path_param_names - set(params))
                msg = (
                    f"Missing path parameter(s) {missing!r} for route "
                    f"{name!r} (path={route.path!r})"
                )
                raise KeyError(msg)
            value = params[param_name]
            if isinstance(value, list):
                msg = (
                    f"Path parameter {param_name!r} got list; path segments "
                    f"must be scalar. Route: {name!r} (path={route.path!r})"
                )
                raise TypeError(msg)
            string_value = str(value)
            encoded_value = (
                quote(string_value, safe="/")
                if seg.param_type == "path"
                else quote(string_value, safe="")
            )
            value_to_validate = encoded_value if seg.param_type == "str" else string_value
            pattern, _ = CONVERTERS[seg.param_type]
            if not re.fullmatch(pattern, value_to_validate):
                msg = (
                    f"Path parameter {param_name!r}={string_value!r} does not "
                    f"match converter '{seg.param_type}' for route {name!r} "
                    f"(path={route.path!r})."
                )
                raise ValueError(msg)
            rendered.append(encoded_value)
            used.add(param_name)
        else:
            rendered.append(seg.value)

    path = "/" + "/".join(rendered) if rendered else "/"

    query_items = [(k, v) for k, v in params.items() if k not in used and v is not None]
    if not query_items:
        return path
    return f"{path}?{urlencode(query_items, doseq=True)}"
