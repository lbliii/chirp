"""Test client for chirp applications.

Uses the same Request and Response types as production.
No wrapper translation layer.
"""

from typing import Any

from chirp.app import App
from chirp.http.response import Response


# ---------------------------------------------------------------------------
# Fragment assertion helpers
# ---------------------------------------------------------------------------


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


class TestClient:
    __test__ = False  # Tell pytest this is not a test class
    """Async test client for chirp applications.

    Returns the same ``Response`` type used in production. Sends requests
    through the ASGI interface directly — no HTTP involved.

    Usage::

        async with TestClient(app) as client:
            response = await client.get("/")
            assert response.status == 200
    """

    __slots__ = ("app",)

    def __init__(self, app: App) -> None:
        self.app = app

    async def __aenter__(self) -> TestClient:
        self.app._ensure_frozen()
        return self

    async def __aexit__(self, *args: object) -> None:
        pass

    async def get(
        self,
        path: str,
        *,
        headers: dict[str, str] | None = None,
        query: dict[str, str] | None = None,
    ) -> Response:
        """Send a GET request."""
        return await self.request("GET", path, headers=headers)

    async def post(
        self,
        path: str,
        *,
        headers: dict[str, str] | None = None,
        body: bytes | None = None,
        json: dict[str, object] | None = None,
    ) -> Response:
        """Send a POST request."""
        extra_headers: dict[str, str] = {}
        request_body = body or b""

        if json is not None:
            import json as json_module

            request_body = json_module.dumps(json).encode("utf-8")
            extra_headers["content-type"] = "application/json"

        merged = {**extra_headers, **(headers or {})}
        return await self.request("POST", path, headers=merged, body=request_body)

    async def put(
        self,
        path: str,
        *,
        headers: dict[str, str] | None = None,
        body: bytes | None = None,
    ) -> Response:
        """Send a PUT request."""
        return await self.request("PUT", path, headers=headers, body=body)

    async def delete(
        self,
        path: str,
        *,
        headers: dict[str, str] | None = None,
    ) -> Response:
        """Send a DELETE request."""
        return await self.request("DELETE", path, headers=headers)

    async def fragment(
        self,
        path: str,
        *,
        method: str = "GET",
        headers: dict[str, str] | None = None,
    ) -> Response:
        """Send a fragment request (sets HX-Request header)."""
        fragment_headers = {"HX-Request": "true"}
        if headers:
            fragment_headers.update(headers)
        return await self.request(method, path, headers=fragment_headers)

    async def request(
        self,
        method: str,
        path: str,
        *,
        headers: dict[str, str] | None = None,
        body: bytes | None = None,
    ) -> Response:
        """Send an arbitrary request through the ASGI app."""
        # Split path and query string
        if "?" in path:
            path_part, query_string = path.split("?", 1)
        else:
            path_part = path
            query_string = ""

        # Build raw ASGI headers
        raw_headers: list[tuple[bytes, bytes]] = []
        for name, value in (headers or {}).items():
            raw_headers.append((name.lower().encode("latin-1"), value.encode("latin-1")))

        # Build ASGI scope
        scope: dict[str, Any] = {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": method.upper(),
            "path": path_part,
            "raw_path": path_part.encode("latin-1"),
            "query_string": query_string.encode("latin-1"),
            "root_path": "",
            "headers": raw_headers,
            "server": ("testserver", 80),
            "client": ("127.0.0.1", 0),
        }

        # Build receive callable
        request_body = body or b""
        body_sent = False

        async def receive() -> dict[str, Any]:
            nonlocal body_sent
            if not body_sent:
                body_sent = True
                return {"type": "http.request", "body": request_body, "more_body": False}
            # After body is sent, wait for disconnect (simplified)
            return {"type": "http.disconnect"}

        # Capture response via send
        response_started = False
        response_status = 200
        response_headers: list[tuple[bytes, bytes]] = []
        response_body_parts: list[bytes] = []

        async def send(message: dict[str, Any]) -> None:
            nonlocal response_started, response_status, response_headers
            if message["type"] == "http.response.start":
                response_started = True
                response_status = message["status"]
                response_headers = list(message.get("headers", []))
            elif message["type"] == "http.response.body":
                response_body_parts.append(message.get("body", b""))

        # Call the ASGI app
        await self.app(scope, receive, send)

        # Build chirp Response from captured data
        body_bytes = b"".join(response_body_parts)

        # Extract content-type from headers
        content_type = "text/html; charset=utf-8"
        extra_headers: list[tuple[str, str]] = []
        for name_b, value_b in response_headers:
            name_str = name_b.decode("latin-1")
            value_str = value_b.decode("latin-1")
            if name_str == "content-type":
                content_type = value_str
            elif name_str != "content-length":
                extra_headers.append((name_str, value_str))

        return Response(
            body=body_bytes,
            status=response_status,
            content_type=content_type,
            headers=tuple(extra_headers),
        )
