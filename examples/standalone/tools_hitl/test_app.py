"""Tests for the tools_hitl example."""

from __future__ import annotations

import re

import pytest

from chirp.testing import TestClient

_FORM_CT = {"content-type": "application/x-www-form-urlencoded"}


def _extract_cookie(response, name: str = "chirp_session") -> str:
    for hname, hvalue in response.headers:
        if hname == "set-cookie" and hvalue.startswith(f"{name}="):
            return hvalue.split(";")[0].partition("=")[2]
    msg = f"Cookie {name!r} not found"
    raise AssertionError(msg)


def _extract_csrf_token(html: str) -> str:
    match = re.search(r'name="_csrf_token" value="([^"]+)"', html)
    assert match is not None
    return match.group(1)


def _session_headers(cookie: str) -> dict[str, str]:
    return {**_FORM_CT, "Cookie": f"chirp_session={cookie}"}


@pytest.mark.issue(442)
class TestToolsHitlExample:
    async def test_index_renders(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/")
            assert response.status == 200
            assert "Tool approval" in response.text

    async def test_agent_pauses_for_approval(self, example_app) -> None:
        async with TestClient(example_app) as client:
            page = await client.get("/")
            cookie = _extract_cookie(page)
            token = _extract_csrf_token(page.text)
            await client.post(
                "/notes",
                body=f"text=Keep+me&_csrf_token={token}".encode(),
                headers=_session_headers(cookie),
            )
            await client.post(
                "/agent/run",
                body=f"_csrf_token={token}".encode(),
                headers=_session_headers(cookie),
            )
            result = await client.sse("/agent/stream", max_events=1, timeout=2.0)
            assert result.events
            assert "delete_all_notes" in result.events[0].data
            assert "Approve" in result.events[0].data

    async def test_approve_clears_notes(self, example_app) -> None:
        async with TestClient(example_app) as client:
            page = await client.get("/")
            cookie = _extract_cookie(page)
            token = _extract_csrf_token(page.text)
            await client.post(
                "/notes",
                body=f"text=Temporary&_csrf_token={token}".encode(),
                headers=_session_headers(cookie),
            )
            await client.post(
                "/agent/run",
                body=f"_csrf_token={token}".encode(),
                headers=_session_headers(cookie),
            )
            pause = await client.sse("/agent/stream", max_events=1, timeout=2.0)
            approval_id = re.search(r'name="approval_id" value="([^"]+)"', pause.events[0].data)
            assert approval_id is not None
            await client.post(
                "/agent/resume",
                body=(
                    f"approval_id={approval_id.group(1)}&decision=approve&_csrf_token={token}"
                ).encode(),
                headers=_session_headers(cookie),
            )
            resume = await client.sse(
                f"/agent/resume/stream?approval_id={approval_id.group(1)}&decision=approve",
                max_events=3,
                timeout=2.0,
            )
            combined = "\n".join(event.data for event in resume.events)
            assert "All notes cleared" in combined
            index = await client.get("/")
            assert "Temporary" not in index.text

    async def test_deny_preserves_notes(self, example_app) -> None:
        async with TestClient(example_app) as client:
            page = await client.get("/")
            cookie = _extract_cookie(page)
            token = _extract_csrf_token(page.text)
            await client.post(
                "/notes",
                body=f"text=Temporary&_csrf_token={token}".encode(),
                headers=_session_headers(cookie),
            )
            await client.post(
                "/agent/run",
                body=f"_csrf_token={token}".encode(),
                headers=_session_headers(cookie),
            )
            pause = await client.sse("/agent/stream", max_events=1, timeout=2.0)
            approval_id = re.search(r'name="approval_id" value="([^"]+)"', pause.events[0].data)
            assert approval_id is not None
            await client.post(
                "/agent/resume",
                body=(
                    f"approval_id={approval_id.group(1)}&decision=deny&_csrf_token={token}"
                ).encode(),
                headers=_session_headers(cookie),
            )
            await client.sse(
                f"/agent/resume/stream?approval_id={approval_id.group(1)}&decision=deny",
                max_events=2,
                timeout=2.0,
            )
            index = await client.get("/")
            assert "Temporary" in index.text
