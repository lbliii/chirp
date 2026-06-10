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

# Leading bytes browsers silently strip before resolving a URL. Tab, newline,
# carriage return, form feed, and other C0 controls plus the space are ignored
# at the *start* of a URL, so an attacker can hide a protocol-relative target
# behind them (e.g. "\t//evil.com" or "\x00//evil.com"). We strip the same set
# before making the safety decision so the value we judge matches what the
# browser will actually navigate to.
_LEADING_STRIP = "".join(chr(c) for c in range(0x21)) + "\x7f"


def is_safe_url(url: str) -> bool:
    r"""Check whether *url* is safe to redirect to.

    A URL is considered safe only if it resolves to a **relative path** on the
    same origin. The decision is made against a *browser-normalized* view of the
    value, because browsers:

    - ignore leading ASCII control characters and whitespace, and
    - treat backslashes (``\``) as forward slashes in the URL path.

    So this function strips leading control/whitespace bytes, rejects any
    leading-backslash form, and normalizes embedded backslashes to forward
    slashes *before* checking that the value:

    - is a non-empty string
    - starts with ``/``
    - does **not** start with ``//`` (protocol-relative URL)
    - does **not** contain ``://`` (absolute URL with scheme)

    This closes the backslash open-redirect: ``"/\evil.com"`` normalizes to
    ``"//evil.com"`` in the browser (a protocol-relative jump to ``evil.com``)
    and is correctly rejected, as is ``"\\evil.com"``. Legitimate relative
    paths are unaffected.

    Examples::

        >>> is_safe_url("/dashboard")
        True
        >>> is_safe_url("/login?next=/home")
        True
        >>> is_safe_url("//evil.com")
        False
        >>> is_safe_url("https://evil.com")
        False
        >>> is_safe_url("/\\evil.com")
        False
        >>> is_safe_url("")
        False
    """
    if not url or not isinstance(url, str):
        return False
    # Browsers ignore leading control/whitespace bytes; strip them so a target
    # hidden behind them (e.g. "\x00//evil.com") is judged on its real form.
    normalized = url.lstrip(_LEADING_STRIP)
    if not normalized:
        return False
    # No legitimate same-origin relative path starts with a backslash. Reject
    # the leading-backslash forms outright ("\evil.com", "\\evil.com") — the
    # browser would normalize them to "/evil.com" / "//evil.com", and treating
    # them as safe is the open-redirect footgun this guard exists to close.
    if normalized.startswith("\\"):
        return False
    # Browsers normalize backslashes to forward slashes in the URL path, so an
    # embedded "\" can still synthesize a protocol-relative ("//") target
    # (e.g. "/\evil.com" -> "//evil.com"). Judge the value as the browser will
    # resolve it.
    normalized = normalized.replace("\\", "/")
    if not normalized.startswith("/"):
        return False
    if normalized.startswith("//"):
        return False
    return "://" not in normalized
