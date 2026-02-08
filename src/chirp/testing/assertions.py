"""Fragment and htmx assertion helpers for chirp tests.

Convenience functions to verify response content in fragment-based
applications and inspect htmx response headers. Each assertion
produces a clear error message on failure.
"""

import json as json_module
from typing import Any

from chirp.http.response import Response


def assert_is_fragment(response: Response, *, status: int = 200) -> None:
    """Assert the response is a fragment (has content, no full page wrapper).

    Checks that the response has the expected status and does **not**
    contain ``<html>`` / ``</html>`` tags that indicate a full page.
    """
    assert response.status == status, (
        f"Expected status {status}, got {response.status}"
    )
    lower = response.text.lower()
    assert "<html>" not in lower, "Response contains full page <html> wrapper"
    assert "</html>" not in lower, "Response contains full page </html> wrapper"
    assert len(response.text.strip()) > 0, "Fragment body is empty"


def assert_fragment_contains(response: Response, text: str) -> None:
    """Assert the fragment response body contains the given text."""
    assert text in response.text, (
        f"Fragment does not contain {text!r}.\n"
        f"Response body: {response.text[:500]}"
    )


def assert_fragment_not_contains(response: Response, text: str) -> None:
    """Assert the fragment response body does **not** contain the given text."""
    assert text not in response.text, (
        f"Fragment unexpectedly contains {text!r}.\n"
        f"Response body: {response.text[:500]}"
    )


def assert_is_error_fragment(response: Response, *, status: int | None = None) -> None:
    """Assert the response is a chirp error fragment snippet.

    Error fragments contain ``class="chirp-error"`` and a ``data-status``
    attribute matching the HTTP status code.
    """
    assert 'class="chirp-error"' in response.text, (
        "Response is not a chirp error fragment (missing class=\"chirp-error\").\n"
        f"Response body: {response.text[:500]}"
    )
    if status is not None:
        assert response.status == status, (
            f"Expected status {status}, got {response.status}"
        )
        assert f'data-status="{status}"' in response.text, (
            f"Error fragment missing data-status=\"{status}\".\n"
            f"Response body: {response.text[:500]}"
        )


# ---------------------------------------------------------------------------
# htmx response header helpers
# ---------------------------------------------------------------------------


def hx_headers(response: Response) -> dict[str, str]:
    """Extract all HX-* response headers into a dict.

    Keys are normalized to canonical htmx casing (e.g. ``HX-Push-Url``)
    regardless of whether the response went through the ASGI sender
    (which lowercases header names per the HTTP spec).

    Useful for quick inspection in tests::

        headers = hx_headers(response)
        assert headers["HX-Redirect"] == "/dashboard"
    """
    result: dict[str, str] = {}
    for name, value in response.headers:
        if name.upper().startswith("HX-"):
            # Normalize: "hx-push-url" / "HX-Push-Url" -> "HX-Push-Url"
            canonical = "HX-" + "-".join(
                p.capitalize() for p in name.split("-")[1:]
            )
            result[canonical] = value
    return result


def assert_hx_redirect(response: Response, url: str) -> None:
    """Assert the response contains an ``HX-Redirect`` header with the given URL."""
    headers = hx_headers(response)
    assert "HX-Redirect" in headers, (
        f"Response has no HX-Redirect header.\n"
        f"HX headers: {headers}"
    )
    assert headers["HX-Redirect"] == url, (
        f"Expected HX-Redirect to be {url!r}, got {headers['HX-Redirect']!r}"
    )


def assert_hx_trigger(
    response: Response,
    event: str | dict[str, Any],
    *,
    after: str | None = None,
) -> None:
    """Assert the response triggers an htmx client-side event.

    Args:
        response: The HTTP response to check.
        event: The event name (string) or event dict to match.
        after: If ``"settle"`` or ``"swap"``, checks the corresponding
            ``HX-Trigger-After-Settle`` or ``HX-Trigger-After-Swap``
            header instead of ``HX-Trigger``.
    """
    if after == "settle":
        header_name = "HX-Trigger-After-Settle"
    elif after == "swap":
        header_name = "HX-Trigger-After-Swap"
    else:
        header_name = "HX-Trigger"

    headers = hx_headers(response)
    assert header_name in headers, (
        f"Response has no {header_name} header.\n"
        f"HX headers: {headers}"
    )
    raw = headers[header_name]

    if isinstance(event, str):
        # Could be a plain string or JSON containing the event name
        if raw == event:
            return
        try:
            parsed = json_module.loads(raw)
            assert event in parsed, (
                f"Event {event!r} not found in {header_name} header {raw!r}"
            )
        except (json_module.JSONDecodeError, TypeError):
            assert raw == event, (
                f"Expected {header_name} to be {event!r}, got {raw!r}"
            )
    else:
        parsed = json_module.loads(raw)
        assert parsed == event, (
            f"Expected {header_name} to be {event!r}, got {parsed!r}"
        )


def assert_hx_retarget(response: Response, selector: str) -> None:
    """Assert the response contains an ``HX-Retarget`` header."""
    headers = hx_headers(response)
    assert "HX-Retarget" in headers, (
        f"Response has no HX-Retarget header.\n"
        f"HX headers: {headers}"
    )
    assert headers["HX-Retarget"] == selector, (
        f"Expected HX-Retarget to be {selector!r}, got {headers['HX-Retarget']!r}"
    )


def assert_hx_reswap(response: Response, strategy: str) -> None:
    """Assert the response contains an ``HX-Reswap`` header."""
    headers = hx_headers(response)
    assert "HX-Reswap" in headers, (
        f"Response has no HX-Reswap header.\n"
        f"HX headers: {headers}"
    )
    assert headers["HX-Reswap"] == strategy, (
        f"Expected HX-Reswap to be {strategy!r}, got {headers['HX-Reswap']!r}"
    )


def assert_hx_push_url(response: Response, url: str) -> None:
    """Assert the response contains an ``HX-Push-Url`` header."""
    headers = hx_headers(response)
    assert "HX-Push-Url" in headers, (
        f"Response has no HX-Push-Url header.\n"
        f"HX headers: {headers}"
    )
    assert headers["HX-Push-Url"] == url, (
        f"Expected HX-Push-Url to be {url!r}, got {headers['HX-Push-Url']!r}"
    )
