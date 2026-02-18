"""URL safety validation for redirect targets.

Prevents open redirect attacks by ensuring redirect URLs are relative
paths on the same origin.

Usage::

    from chirp.security.urls import is_safe_url

    next_url = request.query.get("next", "/")
    if is_safe_url(next_url):
        return Redirect(next_url)
    else:
        return Redirect("/")
"""


def is_safe_url(url: str) -> bool:
    """Check whether *url* is safe to redirect to.

    A URL is considered safe if it is a **relative path** on the same
    origin:

    - Must be a non-empty string
    - Must start with ``/``
    - Must **not** start with ``//`` (protocol-relative URL)
    - Must **not** contain ``://`` (absolute URL with scheme)

    Examples::

        >>> is_safe_url("/dashboard")
        True
        >>> is_safe_url("/login?next=/home")
        True
        >>> is_safe_url("//evil.com")
        False
        >>> is_safe_url("https://evil.com")
        False
        >>> is_safe_url("")
        False
    """
    if not url or not isinstance(url, str):
        return False
    if not url.startswith("/"):
        return False
    if url.startswith("//"):
        return False
    return "://" not in url
