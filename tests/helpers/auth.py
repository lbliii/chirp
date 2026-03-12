"""Auth-related test helpers — CSRF and session cookie extraction."""

import re


def extract_csrf_token(html: str) -> str | None:
    """Extract CSRF token from rendered HTML (hidden input or meta tag).

    Supports:
    - ``<input name="_csrf_token" value="...">``
    - ``<input value="..." name="_csrf_token">``
    - ``<meta name="csrf-token" content="...">``
    """
    patterns = (
        r'name="_csrf_token" value="([^"]+)"',
        r'value="([^"]+)"[^>]*name="_csrf_token"',
        r'<input[^>]*name="_csrf_token"[^>]*value="([^"]+)"',
        r'<input[^>]*value="([^"]+)"[^>]*name="_csrf_token"',
        r'<meta[^>]*name="csrf-token"[^>]*content="([^"]+)"',
        r'<meta[^>]*content="([^"]+)"[^>]*name="csrf-token"',
    )
    for pattern in patterns:
        match = re.search(pattern, html)
        if match:
            return match.group(1)
    return None


def extract_session_cookie(response: object, cookie_name: str = "chirp_session") -> str | None:
    """Extract a Set-Cookie value from response headers.

    Args:
        response: Response-like object with a ``headers`` attribute
            yielding (name, value) pairs.
        cookie_name: Cookie name to extract (default ``chirp_session``).

    Returns:
        The cookie value, or None if not found.
    """
    headers = getattr(response, "headers", ())
    for hname, hvalue in headers:
        if hname.lower() == "set-cookie" and hvalue.startswith(f"{cookie_name}="):
            return hvalue.split(";")[0].partition("=")[2]
    return None
