"""Tests for the chat example — SSE + POST bidirectional communication."""

from chirp.testing import TestClient

_FORM_CT = {"Content-Type": "application/x-www-form-urlencoded"}


def _extract_cookie(response, name: str = "chirp_session") -> str | None:
    """Extract a Set-Cookie value from response headers."""
    for hname, hvalue in response.headers:
        if hname == "set-cookie" and hvalue.startswith(f"{name}="):
            return hvalue.split(";")[0].partition("=")[2]
    return None


async def _login(client, username: str = "alice") -> dict[str, str]:
    """Log in and return headers with session cookie."""
    response = await client.post(
        "/login",
        body=f"username={username}".encode(),
        headers=_FORM_CT,
    )
    cookie = _extract_cookie(response)
    headers: dict[str, str] = {}
    if cookie:
        headers["Cookie"] = f"chirp_session={cookie}"
    return headers


class TestLoginFlow:
    """Login page and session management."""

    async def test_index_redirects_to_login(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/")
            assert response.status == 302
            assert "/login" in response.headers.get("location", "")

    async def test_login_page_renders(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/login")
            assert response.status == 200
            assert "Join Chat" in response.text

    async def test_login_sets_session(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.post(
                "/login",
                body=b"username=alice",
                headers=_FORM_CT,
            )
            assert response.status == 302
            assert "/chat" in response.headers.get("location", "")
            assert _extract_cookie(response) is not None

    async def test_empty_username_shows_error(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.post(
                "/login",
                body=b"username=",
                headers=_FORM_CT,
            )
            assert response.status == 200
            assert "required" in response.text.lower()

    async def test_chat_redirects_without_login(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/chat")
            assert response.status == 302
            assert "/login" in response.headers.get("location", "")

    async def test_index_redirects_to_chat_when_logged_in(self, example_app) -> None:
        async with TestClient(example_app) as client:
            auth = await _login(client)
            response = await client.get("/", headers=auth)
            assert response.status == 302
            assert "/chat" in response.headers.get("location", "")


class TestChatPage:
    """Chat page rendering."""

    async def test_chat_page_renders(self, example_app) -> None:
        async with TestClient(example_app) as client:
            auth = await _login(client)
            response = await client.get("/chat", headers=auth)
            assert response.status == 200
            assert "Chat Room" in response.text
            assert "alice" in response.text

    async def test_chat_page_has_sse_connection(self, example_app) -> None:
        async with TestClient(example_app) as client:
            auth = await _login(client)
            response = await client.get("/chat", headers=auth)
            assert 'sse-connect="/chat/events"' in response.text


class TestSendMessage:
    """POST /chat/send — message submission."""

    async def test_send_returns_204(self, example_app) -> None:
        async with TestClient(example_app) as client:
            auth = await _login(client)
            response = await client.post(
                "/chat/send",
                body=b"message=hello+world",
                headers={**_FORM_CT, **auth},
            )
            assert response.status == 204

    async def test_empty_message_returns_204(self, example_app) -> None:
        async with TestClient(example_app) as client:
            auth = await _login(client)
            response = await client.post(
                "/chat/send",
                body=b"message=",
                headers={**_FORM_CT, **auth},
            )
            assert response.status == 204

    async def test_send_without_login_returns_401(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.post(
                "/chat/send",
                body=b"message=hello",
                headers=_FORM_CT,
            )
            assert response.status == 401


class TestSSEStream:
    """GET /chat/events — SSE message stream."""

    async def test_sse_connects(self, example_app) -> None:
        """SSE endpoint returns event-stream content type."""
        async with TestClient(example_app) as client:
            result = await client.sse("/chat/events", max_events=0, timeout=0.5)
            assert result.status == 200
            assert result.headers.get("content-type") == "text/event-stream"
