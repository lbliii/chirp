"""Cookie parsing and SetCookie serialization.

Consolidates the read side (parse_cookies, used by Request) and the
write side (SetCookie, used by Response) in one module.
"""

from dataclasses import dataclass


def parse_cookies(header: str) -> dict[str, str]:
    """Parse a ``Cookie`` header value into a name-value dict.

    Returns an empty dict for empty or missing headers.
    """
    if not header:
        return {}
    cookies: dict[str, str] = {}
    for pair in header.split(";"):
        pair = pair.strip()
        if "=" in pair:
            key, _, value = pair.partition("=")
            cookies[key.strip()] = value.strip()
    return cookies


@dataclass(frozen=True, slots=True)
class SetCookie:
    """A ``Set-Cookie`` directive attached to a Response."""

    name: str
    value: str
    max_age: int | None = None
    path: str = "/"
    domain: str | None = None
    secure: bool = False
    httponly: bool = True
    samesite: str = "lax"

    def to_header_value(self) -> str:
        """Serialize to a ``Set-Cookie`` header value string."""
        parts = [f"{self.name}={self.value}"]
        if self.max_age is not None:
            parts.append(f"Max-Age={self.max_age}")
        if self.path:
            parts.append(f"Path={self.path}")
        if self.domain:
            parts.append(f"Domain={self.domain}")
        if self.secure:
            parts.append("Secure")
        if self.httponly:
            parts.append("HttpOnly")
        if self.samesite:
            parts.append(f"SameSite={self.samesite}")
        return "; ".join(parts)
