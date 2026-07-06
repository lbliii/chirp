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
    assert response.status == status, f"Expected status {status}, got {response.status}"
    lower = response.text.lower()
    assert "<html>" not in lower, "Response contains full page <html> wrapper"
    assert "</html>" not in lower, "Response contains full page </html> wrapper"
    assert len(response.text.strip()) > 0, "Fragment body is empty"


def assert_no_full_document(response: Response) -> None:
    """Assert an htmx response did not accidentally return a full HTML document."""
    lower = response.text.lower()
    assert "<html" not in lower, "Response contains a full document <html> tag"
    assert "<!doctype" not in lower, "Response contains a full document doctype"


def assert_is_full_page(response: Response, *, status: int = 200) -> None:
    """Assert the response is a full page document."""
    assert response.status == status, f"Expected status {status}, got {response.status}"
    lower = response.text.lower()
    assert "<html" in lower or "<!doctype" in lower, (
        f"Response does not look like a full page document.\nResponse body: {response.text[:500]}"
    )


def assert_has_id(response: Response, element_id: str) -> None:
    """Assert the response body contains an element with the given id."""
    import re

    pattern = rf"""id\s*=\s*["']{re.escape(element_id)}["']"""
    assert re.search(pattern, response.text), (
        f"Response has no element id={element_id!r}.\nResponse body: {response.text[:500]}"
    )


def assert_fragment_contains(response: Response, text: str) -> None:
    """Assert the fragment response body contains the given text."""
    assert text in response.text, (
        f"Fragment does not contain {text!r}.\nResponse body: {response.text[:500]}"
    )


def assert_fragment_not_contains(response: Response, text: str) -> None:
    """Assert the fragment response body does **not** contain the given text."""
    assert text not in response.text, (
        f"Fragment unexpectedly contains {text!r}.\nResponse body: {response.text[:500]}"
    )


def assert_is_error_fragment(response: Response, *, status: int | None = None) -> None:
    """Assert the response is a chirp error fragment snippet.

    Error fragments contain the ``chirp-error`` CSS class and a ``data-status``
    attribute matching the HTTP status code.
    """
    import re

    has_class = bool(re.search(r'class="[^"]*\bchirp-error\b[^"]*"', response.text))
    assert has_class, (
        "Response is not a chirp error fragment (missing chirp-error class).\n"
        f"Response body: {response.text[:500]}"
    )
    if status is not None:
        assert response.status == status, f"Expected status {status}, got {response.status}"
        assert f'data-status="{status}"' in response.text, (
            f'Error fragment missing data-status="{status}".\nResponse body: {response.text[:500]}'
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
            canonical = "HX-" + "-".join(p.capitalize() for p in name.split("-")[1:])
            result[canonical] = value
    return result


def assert_hx_redirect(response: Response, url: str) -> None:
    """Assert the response contains an ``HX-Redirect`` header with the given URL."""
    headers = hx_headers(response)
    assert "HX-Redirect" in headers, f"Response has no HX-Redirect header.\nHX headers: {headers}"
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

    Timing variants are htmx 2/generic wire assertions only. Htmx 4 removed
    both ``After`` response headers, so a passing assertion does not prove
    browser delivery under the htmx 4 preview; use a browser lifecycle test.

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
    timing_note = (
        " This is an htmx 2/generic wire header; htmx 4 behavior requires a "
        "browser lifecycle assertion."
        if after in {"settle", "swap"}
        else ""
    )
    assert header_name in headers, (
        f"Response has no {header_name} header.{timing_note}\nHX headers: {headers}"
    )
    raw = headers[header_name]

    if isinstance(event, str):
        # Could be a plain string or JSON containing the event name
        if raw == event:
            return
        try:
            parsed = json_module.loads(raw)
            assert event in parsed, f"Event {event!r} not found in {header_name} header {raw!r}"
        except json_module.JSONDecodeError, TypeError:
            assert raw == event, f"Expected {header_name} to be {event!r}, got {raw!r}"
    else:
        parsed = json_module.loads(raw)
        assert parsed == event, f"Expected {header_name} to be {event!r}, got {parsed!r}"


def assert_hx_retarget(response: Response, selector: str) -> None:
    """Assert the response contains an ``HX-Retarget`` header."""
    headers = hx_headers(response)
    assert "HX-Retarget" in headers, f"Response has no HX-Retarget header.\nHX headers: {headers}"
    assert headers["HX-Retarget"] == selector, (
        f"Expected HX-Retarget to be {selector!r}, got {headers['HX-Retarget']!r}"
    )


def assert_hx_reswap(response: Response, strategy: str) -> None:
    """Assert the response contains an ``HX-Reswap`` header."""
    headers = hx_headers(response)
    assert "HX-Reswap" in headers, f"Response has no HX-Reswap header.\nHX headers: {headers}"
    assert headers["HX-Reswap"] == strategy, (
        f"Expected HX-Reswap to be {strategy!r}, got {headers['HX-Reswap']!r}"
    )


def assert_hx_push_url(response: Response, url: str) -> None:
    """Assert the response contains an ``HX-Push-Url`` header."""
    headers = hx_headers(response)
    assert "HX-Push-Url" in headers, f"Response has no HX-Push-Url header.\nHX headers: {headers}"
    assert headers["HX-Push-Url"] == url, (
        f"Expected HX-Push-Url to be {url!r}, got {headers['HX-Push-Url']!r}"
    )


# ---------------------------------------------------------------------------
# Status and OOB assertion helpers
# ---------------------------------------------------------------------------


def assert_status(response: Response, status: int) -> None:
    """Assert the response has the expected HTTP status code."""
    assert response.status == status, f"Expected status {status}, got {response.status}"


def assert_oob_targets(response: Response, *target_ids: str) -> None:
    """Assert the response contains OOB swap elements for each target ID.

    Checks that the response body includes ``hx-swap-oob`` attributes
    targeting the given element IDs — the pattern produced by ``OOB()``
    return values.

    Usage::

        response = await client.post("/save")
        assert_oob_targets(response, "item-row", "count")
    """
    import re

    body = response.text
    found_ids: set[str] = set()
    for match in re.finditer(r'id=["\']([^"\']+)["\'][^>]*hx-swap-oob', body):
        found_ids.add(match.group(1))
    for match in re.finditer(r'hx-swap-oob=["\'][^"\']*["\'][^>]*id=["\']([^"\']+)["\']', body):
        found_ids.add(match.group(1))

    missing = set(target_ids) - found_ids
    assert not missing, (
        f"OOB targets missing from response: {sorted(missing)}.\n"
        f"Found OOB targets: {sorted(found_ids)}\n"
        f"Response body: {body[:500]}"
    )


def assert_mutation_redirect(response: Response, url: str, *, status: int = 303) -> None:
    """Assert the response is a mutation redirect (non-htmx POST result).

    Checks for a 303 (or custom status) redirect to the given URL —
    the pattern produced by ``MutationResult`` for non-htmx requests.

    Usage::

        response = await client.post("/save")
        assert_mutation_redirect(response, "/items")
    """
    assert response.status == status, f"Expected redirect status {status}, got {response.status}"
    location = dict(response.headers).get("location", "")
    assert location == url, f"Expected redirect to {url!r}, got {location!r}"


def assert_mutation_fragments(response: Response, *target_ids: str) -> None:
    """Assert the response is an htmx mutation with OOB fragments.

    Checks for a 200 status (htmx inline swap) and verifies the
    expected OOB swap targets are present — the pattern produced by
    ``MutationResult`` with fragments for htmx requests.

    Usage::

        response = await client.post("/save", headers=hx_request_headers)
        assert_mutation_fragments(response, "item-row", "count")
    """
    assert response.status == 200, f"Expected status 200, got {response.status}"
    if target_ids:
        assert_oob_targets(response, *target_ids)
