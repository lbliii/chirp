"""Route smoke helpers for full-page and fragment render checks."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any, Literal

from chirp.http.response import Response
from chirp.testing.assertions import (
    assert_is_fragment,
    assert_is_full_page,
    assert_no_full_document,
    assert_status,
)

type RouteSmokeMode = Literal["status", "full_page", "fragment", "boosted", "both"]


@dataclass(frozen=True, slots=True)
class RouteSmokeCase:
    """One route/render-intent expectation for ``assert_route_smoke``."""

    path: str
    mode: RouteSmokeMode = "full_page"
    status: int = 200
    name: str | None = None
    template: str | None = None
    block: str | None = None
    target: str | None = None


def _normalize_case(case: RouteSmokeCase | str) -> RouteSmokeCase:
    if isinstance(case, str):
        return RouteSmokeCase(case)
    return case


def _case_label(case: RouteSmokeCase, intent: str) -> str:
    parts = [f"path={case.path!r}", f"intent={intent}"]
    if case.name:
        parts.append(f"name={case.name!r}")
    if case.template:
        parts.append(f"template={case.template!r}")
    if case.block:
        parts.append(f"block={case.block!r}")
    if case.target:
        parts.append(f"target={case.target!r}")
    return ", ".join(parts)


def _response_render_intent(response: Response) -> str:
    return response.header("X-Chirp-Render-Intent") or response.render_intent


def _observed_render_shape(response: Response) -> str:
    body = response.text.strip().lower()
    if "<!doctype" in body or "<html" in body:
        if _response_render_intent(response) == "fragment":
            return "boosted_outlet_document"
        return "full_document"
    if not body:
        return "empty"
    if body.startswith("<"):
        return "html_fragment"
    return "text"


def _wrap_failure(
    case: RouteSmokeCase,
    intent: str,
    exc: BaseException,
    response: Response | None = None,
) -> AssertionError:
    details = _case_label(case, intent)
    if response is not None:
        details = (
            f"{details}, observed_shape={_observed_render_shape(response)!r}, "
            f"status={response.status}"
        )
    return AssertionError(f"Route smoke failed ({details}): {exc}")


def _assert_boosted_render_shape(response: Response) -> None:
    render_intent = _response_render_intent(response)
    if render_intent == "full_page":
        raise AssertionError(
            "Boosted response has full_page render intent; return Page/Page.mounted "
            "for shell-outlet negotiation instead of Template."
        )
    if render_intent != "fragment":
        assert_no_full_document(response)


async def _assert_full(client: Any, case: RouteSmokeCase) -> Response:
    response: Response | None = None
    try:
        response = await client.get(case.path)
        assert_is_full_page(response, status=case.status)
        return response
    except AssertionError as exc:
        raise _wrap_failure(case, "full_page", exc, response) from exc
    except Exception as exc:
        raise _wrap_failure(case, "full_page", exc, response) from exc


async def _assert_fragment(client: Any, case: RouteSmokeCase) -> Response:
    response: Response | None = None
    try:
        response = await client.fragment(case.path, target=case.target)
        assert_is_fragment(response, status=case.status)
        return response
    except AssertionError as exc:
        raise _wrap_failure(case, "fragment", exc, response) from exc
    except Exception as exc:
        raise _wrap_failure(case, "fragment", exc, response) from exc


async def _assert_boosted(client: Any, case: RouteSmokeCase) -> Response:
    if not case.target:
        raise ValueError(
            f"Boosted route smoke requires a target for {case.path!r}; "
            "set RouteSmokeCase(..., mode='boosted', target='main')."
        )

    response: Response | None = None
    try:
        response = await client.boosted(case.path, target=case.target)
        assert_status(response, case.status)
        _assert_boosted_render_shape(response)
        return response
    except AssertionError as exc:
        raise _wrap_failure(case, "boosted", exc, response) from exc
    except Exception as exc:
        raise _wrap_failure(case, "boosted", exc, response) from exc


async def _assert_status(client: Any, case: RouteSmokeCase) -> Response:
    response: Response | None = None
    try:
        response = await client.get(case.path)
        assert_status(response, case.status)
        return response
    except AssertionError as exc:
        raise _wrap_failure(case, "status", exc, response) from exc
    except Exception as exc:
        raise _wrap_failure(case, "status", exc, response) from exc


async def assert_route_smoke(
    client: Any,
    cases: Iterable[RouteSmokeCase | str],
) -> dict[tuple[str, str], Response]:
    """Assert route status/render mode expectations through a ``TestClient``.

    ``str`` cases smoke a full-page route at status 200. Use ``RouteSmokeCase``
    when a route should be checked as a fragment, boosted shell outlet,
    status-only response, or both full-page and fragment render intents.
    """
    responses: dict[tuple[str, str], Response] = {}
    for raw_case in cases:
        case = _normalize_case(raw_case)
        if case.mode == "status":
            responses[(case.path, "status")] = await _assert_status(client, case)
        elif case.mode == "full_page":
            responses[(case.path, "full_page")] = await _assert_full(client, case)
        elif case.mode == "fragment":
            responses[(case.path, "fragment")] = await _assert_fragment(client, case)
        elif case.mode == "boosted":
            responses[(case.path, "boosted")] = await _assert_boosted(client, case)
        elif case.mode == "both":
            responses[(case.path, "full_page")] = await _assert_full(client, case)
            responses[(case.path, "fragment")] = await _assert_fragment(client, case)
        else:
            raise ValueError(
                f"Unsupported route smoke mode {case.mode!r} for {case.path!r}. "
                "Expected 'status', 'full_page', 'fragment', 'boosted', or 'both'."
            )
    return responses
