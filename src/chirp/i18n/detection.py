"""Locale detection strategies — header, cookie, URL prefix."""

from chirp.http.request import Request


def detect_from_header(request: Request, supported: tuple[str, ...]) -> str | None:
    """Detect locale from Accept-Language header."""
    accept = request.headers.get("accept-language", "")
    if not accept:
        return None

    # Parse Accept-Language: en-US,en;q=0.9,es;q=0.8
    locales = []
    for part in accept.split(","):
        part = part.strip()
        if ";q=" in part:
            lang, q = part.split(";q=", 1)
            try:
                quality = float(q.strip())
            except ValueError:
                quality = 0.0
        else:
            lang = part
            quality = 1.0
        locales.append((lang.strip().lower(), quality))

    locales.sort(key=lambda x: x[1], reverse=True)

    for lang, _ in locales:
        # Exact match
        if lang in supported:
            return lang
        # Language-only match (en-US -> en)
        base = lang.split("-")[0]
        if base in supported:
            return base

    return None


def detect_from_cookie(request: Request, cookie_name: str) -> str | None:
    """Detect locale from a cookie."""
    return request.cookies.get(cookie_name)


def detect_from_url_prefix(request: Request, supported: tuple[str, ...]) -> str | None:
    """Detect locale from URL prefix (e.g., /es/page)."""
    path = request.path
    if len(path) < 2:
        return None
    parts = path.strip("/").split("/", 1)
    if parts and parts[0] in supported:
        return parts[0]
    return None
