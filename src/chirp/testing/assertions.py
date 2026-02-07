"""Fragment assertion helpers for chirp tests.

Convenience functions to verify response content in fragment-based
applications. Each assertion produces a clear error message on failure.
"""

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
