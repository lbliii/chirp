"""Auth-related test helpers — CSRF and session cookie extraction.

Also provides login/CSRF flow helpers for apps that wire ``AuthMiddleware`` +
``CSRFMiddleware`` (e.g. the lucky_cat example). Both the CSRF token and the
session cookie rotate per response, so a mutation must pair the token with the
cookie from the *same* render and carry the rotated cookie forward — the helpers
below encapsulate that.
"""

import re
from typing import Any


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


async def login(
    client: Any,
    *,
    username: str,
    password: str,
    cookie_name: str = "chirp_session",
    next_url: str = "/",
) -> str | None:
    """Perform the sign-in flow and return the authenticated session cookie.

    GETs ``/login`` for a CSRF token + session cookie, POSTs the credentials,
    and returns the regenerated (authenticated) session cookie. The returned
    cookie is valid for subsequent GET requests (e.g. asserting signed-in chrome).
    """
    page = await client.get("/login")
    csrf = extract_csrf_token(page.text)
    cookie = extract_session_cookie(page, cookie_name=cookie_name)
    headers: dict[str, str] = {"HX-Request": "true"}
    if csrf:
        headers["X-CSRF-Token"] = csrf
    if cookie:
        headers["Cookie"] = f"{cookie_name}={cookie}"
    resp = await client.post(
        "/login",
        data={"username": username, "password": password, "next": next_url},
        headers=headers,
    )
    return extract_session_cookie(resp, cookie_name=cookie_name) or cookie


async def csrf_post(
    client: Any,
    path: str,
    *,
    cookie: str | None,
    cookie_name: str = "chirp_session",
    data: dict[str, Any] | None = None,
    htmx: bool = True,
    via: str = "/",
    extra_headers: dict[str, str] | None = None,
) -> tuple[Any, str | None]:
    """POST ``path`` with a CSRF token + session cookie paired from one render.

    The CSRF token and the session cookie rotate per response, so this GETs
    ``via`` (sending the current ``cookie``), reads the token AND the re-issued
    cookie from that *same* response, and POSTs with the matched pair. Returns
    ``(response, latest_cookie)`` so a follow-up mutation can thread the cookie
    rotated by the POST.
    """
    get_headers = {"Cookie": f"{cookie_name}={cookie}"} if cookie else {}
    page = await client.get(via, headers=get_headers)
    csrf = extract_csrf_token(page.text)
    current = extract_session_cookie(page, cookie_name=cookie_name) or cookie
    headers: dict[str, str] = {}
    if csrf:
        headers["X-CSRF-Token"] = csrf
    if htmx:
        headers["HX-Request"] = "true"
    if current:
        headers["Cookie"] = f"{cookie_name}={current}"
    if extra_headers:
        headers.update(extra_headers)
    resp = await client.post(path, data=data or {}, headers=headers)
    latest = extract_session_cookie(resp, cookie_name=cookie_name) or current
    return resp, latest
