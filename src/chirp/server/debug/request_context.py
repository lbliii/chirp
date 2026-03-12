"""Request context extraction for debug page with sensitive-header masking."""

from typing import Any

from chirp.http.headers import SENSITIVE_HEADER_NAMES


def _extract_request_context(request: Any) -> dict[str, Any]:
    """Extract displayable request context from a chirp Request."""
    ctx: dict[str, Any] = {
        "method": getattr(request, "method", "?"),
        "path": getattr(request, "path", "?"),
        "http_version": getattr(request, "http_version", "?"),
    }

    # Headers with sensitive value masking
    headers = getattr(request, "headers", None)
    if headers:
        masked: list[tuple[str, str]] = []
        # Headers may be a Headers object or dict-like
        items = headers.items() if hasattr(headers, "items") else []
        for name, value in items:
            name_lower = name.lower() if isinstance(name, str) else name
            if name_lower in SENSITIVE_HEADER_NAMES:
                masked.append((str(name), "••••••••"))
            else:
                masked.append((str(name), str(value)))
        ctx["headers"] = masked

    # Query parameters
    query = getattr(request, "query", None)
    if query:
        items = query.items() if hasattr(query, "items") else []
        ctx["query"] = [(str(k), str(v)) for k, v in items]

    # Path params (from route match)
    path_params = getattr(request, "path_params", None)
    if path_params:
        ctx["path_params"] = dict(path_params)

    # Client address
    client = getattr(request, "client", None)
    if client:
        ctx["client"] = f"{client[0]}:{client[1]}"

    return ctx
