"""Boosted-navigation matrix tests.

Parametrized integration tests covering shell_a/shell_b/no-shell source
shells crossed with same-shell/cross-shell/no-shell destinations and
valid/invalid/missing HX-Target values.

Every cell asserts the headline invariant: **a boosted GET never 500s on
a malformed or cross-shell request.** It either renders a valid fragment
or emits ``HX-Redirect`` so the browser can re-navigate.

See ``.context/navigation-matrix.md`` for the axis design.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import pytest

from chirp.http.request import Request
from chirp.http.response import Response
from chirp.pages.types import LayoutChain, LayoutInfo
from chirp.routing.route import Route
from chirp.routing.router import Router
from chirp.server.handler import create_request_handler
from chirp.templating.fragment_target_registry import FragmentTargetRegistry

# ---------------------------------------------------------------------------
# Fixture scaffolding
# ---------------------------------------------------------------------------


_SHELL_A = LayoutInfo(
    "pages/shell_a/_layout.html",
    "body",
    0,
    domain_name="shell_a",
    swap_scope_name="shell_a",
    outlet_target_id="site-content",
)
_SHELL_B = LayoutInfo(
    "pages/shell_b/_layout.html",
    "body",
    0,
    domain_name="shell_b",
    swap_scope_name="shell_b",
    outlet_target_id="shell-b-content",
)


def _build_layout_chains() -> dict[str, LayoutChain]:
    """Multiple routes per shell so same-shell navigation has distinct paths.

    - ``/a`` and ``/a2`` live in ``shell_a`` (outlet ``site-content``)
    - ``/b`` and ``/b2`` live in ``shell_b`` (outlet ``shell-b-content``)
    - ``/plain`` has no layout chain — unshelled route.
    """
    return {
        "/a": LayoutChain((_SHELL_A,)),
        "/a2": LayoutChain((_SHELL_A,)),
        "/b": LayoutChain((_SHELL_B,)),
        "/b2": LayoutChain((_SHELL_B,)),
    }


def _build_fragment_registry() -> FragmentTargetRegistry:
    reg = FragmentTargetRegistry()
    reg.register("site-content", fragment_block="content", scope_name="shell_a")
    reg.register("shell-b-content", fragment_block="content", scope_name="shell_b")
    reg.freeze()
    return reg


def _build_router() -> Router:
    router = Router()
    router.add(Route("/a", lambda: "in-shell-a", frozenset({"GET"})))
    router.add(Route("/a2", lambda: "in-shell-a-2", frozenset({"GET"})))
    router.add(Route("/b", lambda: "in-shell-b", frozenset({"GET"})))
    router.add(Route("/b2", lambda: "in-shell-b-2", frozenset({"GET"})))
    router.add(Route("/plain", lambda: "no-shell", frozenset({"GET"})))
    router.compile()
    return router


Scenario = Literal["full", "missing_registries", "no_shell"]


def _make_handler(scenario: Scenario):
    """Build a request handler with the requested registry state."""
    router = _build_router()
    if scenario == "full":
        return create_request_handler(
            router=router,
            middleware=(),
            tool_registry=None,
            mcp_path="/mcp",
            debug=False,
            providers=None,
            kida_env=None,
            fragment_target_registry=_build_fragment_registry(),
            route_layout_chains=_build_layout_chains(),
            swap_scope_map={"shell_a": "site-content", "shell_b": "shell-b-content"},
        )
    if scenario == "missing_registries":
        return create_request_handler(
            router=router,
            middleware=(),
            tool_registry=None,
            mcp_path="/mcp",
            debug=False,
            providers=None,
            kida_env=None,
            fragment_target_registry=None,
            route_layout_chains=None,
            swap_scope_map={"shell_a": "site-content"},
        )
    if scenario == "no_shell":
        return create_request_handler(
            router=router,
            middleware=(),
            tool_registry=None,
            mcp_path="/mcp",
            debug=False,
            providers=None,
            kida_env=None,
            fragment_target_registry=None,
            route_layout_chains=None,
            swap_scope_map={},
        )
    raise AssertionError(f"unknown scenario {scenario!r}")


def _boosted_request(
    *,
    path: str,
    current_url: str,
    hx_target: bytes | None,
    include_hx_request: bool = True,
    request_type: bytes | None = None,
) -> Request:
    async def _receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    headers: list[tuple[bytes, bytes]] = [(b"hx-boosted", b"true")]
    if include_hx_request:
        headers.append((b"hx-request", b"true"))
    headers.append((b"hx-current-url", current_url.encode()))
    if hx_target is not None:
        headers.append((b"hx-target", hx_target))
    if request_type is not None:
        headers.append((b"hx-request-type", request_type))
        headers.append((b"accept", b"text/html"))

    return Request.from_asgi(
        {
            "type": "http",
            "method": "GET",
            "path": path,
            "headers": headers,
            "query_string": b"",
            "http_version": "1.1",
            "server": ("127.0.0.1", 8000),
            "client": ("127.0.0.1", 12345),
        },
        _receive,
    )


# ---------------------------------------------------------------------------
# Shared invariant helper
# ---------------------------------------------------------------------------


def _hx_redirect(response: Response) -> str | None:
    for name, value in response.headers:
        if name.lower() == "hx-redirect":
            return value
    return None


def _assert_boost_invariants(response: Response) -> None:
    """Invariants that apply to *every* cell — no exceptions."""
    assert isinstance(response, Response), f"expected Response, got {type(response)!r}"
    # Headline invariant: boosted GETs never 500.
    assert response.status != 500, (
        f"boosted GET produced a 500 response (body={response.text[:200]!r})"
    )
    # Fragment responses must never leak <!DOCTYPE.
    if response.render_intent == "fragment":
        body_text = (
            response.text
            if isinstance(response.body, str)
            else response.body.decode("utf-8", "replace")
        )
        assert "<!DOCTYPE" not in body_text.upper(), (
            "fragment body contains <!DOCTYPE (full page leaked into outlet)"
        )


# ---------------------------------------------------------------------------
# Matrix cells
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class MatrixCase:
    id: str
    scenario: Scenario
    current_url: str
    dest_path: str
    hx_target: bytes | None
    expected_status: int
    expects_redirect: bool
    expected_body_contains: str | None = None
    include_hx_request: bool = True
    request_type: bytes | None = None


SITE = "site-content"
SHELLB = "shell-b-content"

CASES: tuple[MatrixCase, ...] = (
    # --- Happy-path: same-shell boosted navigation (/a → /a2) ---
    MatrixCase(
        id="01_happy_same_shell_hashed",
        scenario="full",
        current_url="http://127.0.0.1:8000/a",
        dest_path="/a2",
        hx_target=b"#" + SITE.encode(),
        expected_status=200,
        expects_redirect=False,
        expected_body_contains="in-shell-a-2",
    ),
    MatrixCase(
        id="02_happy_same_shell_bare",
        scenario="full",
        current_url="http://127.0.0.1:8000/a",
        dest_path="/a2",
        hx_target=SITE.encode(),
        expected_status=200,
        expects_redirect=False,
        expected_body_contains="in-shell-a-2",
    ),
    MatrixCase(
        id="02b_happy_same_shell_htmx4_tagged",
        scenario="full",
        current_url="http://127.0.0.1:8000/a",
        dest_path="/a2",
        hx_target=b"main#site-content",
        expected_status=200,
        expects_redirect=False,
        expected_body_contains="in-shell-a-2",
        request_type=b"partial",
    ),
    # --- Same-shell, client sent an unsatisfiable target → mismatch redirect ---
    MatrixCase(
        id="03_same_shell_unsatisfiable_target",
        scenario="full",
        current_url="http://127.0.0.1:8000/a",
        dest_path="/a2",
        hx_target=b"#does-not-exist",
        expected_status=200,
        expects_redirect=True,
    ),
    MatrixCase(
        id="04_same_shell_missing_target",
        scenario="full",
        current_url="http://127.0.0.1:8000/a",
        dest_path="/a2",
        hx_target=None,
        expected_status=200,
        expects_redirect=True,
    ),
    # --- Cross-shell navigation: any target → redirect ---
    MatrixCase(
        id="05_cross_shell_with_source_target",
        scenario="full",
        current_url="http://127.0.0.1:8000/a",
        dest_path="/b",
        hx_target=b"#" + SITE.encode(),
        expected_status=200,
        expects_redirect=True,
    ),
    MatrixCase(
        id="06_cross_shell_with_dest_target",
        scenario="full",
        current_url="http://127.0.0.1:8000/a",
        dest_path="/b",
        hx_target=b"#" + SHELLB.encode(),
        expected_status=200,
        expects_redirect=True,
    ),
    MatrixCase(
        id="07_cross_shell_missing_target",
        scenario="full",
        current_url="http://127.0.0.1:8000/a",
        dest_path="/b",
        hx_target=None,
        expected_status=200,
        expects_redirect=True,
    ),
    # --- Reverse cross-shell (shell B → shell A) ---
    MatrixCase(
        id="08_reverse_cross_shell",
        scenario="full",
        current_url="http://127.0.0.1:8000/b",
        dest_path="/a",
        hx_target=b"#" + SHELLB.encode(),
        expected_status=200,
        expects_redirect=True,
    ),
    MatrixCase(
        id="09_happy_same_shell_b",
        scenario="full",
        current_url="http://127.0.0.1:8000/b",
        dest_path="/b2",
        hx_target=b"#" + SHELLB.encode(),
        expected_status=200,
        expects_redirect=False,
        expected_body_contains="in-shell-b-2",
    ),
    # --- Inconsistent setup: shell configured, registries None → Sprint 2.1 ---
    MatrixCase(
        id="10_inconsistent_registries_with_shell",
        scenario="missing_registries",
        current_url="http://127.0.0.1:8000/a",
        dest_path="/a",
        hx_target=b"#" + SITE.encode(),
        expected_status=200,
        expects_redirect=True,
    ),
    MatrixCase(
        id="11_inconsistent_registries_missing_target",
        scenario="missing_registries",
        current_url="http://127.0.0.1:8000/a",
        dest_path="/a",
        hx_target=None,
        expected_status=200,
        expects_redirect=True,
    ),
    # --- No-shell app: passes through normal dispatch ---
    MatrixCase(
        id="12_no_shell_plain_navigation",
        scenario="no_shell",
        current_url="http://127.0.0.1:8000/plain",
        dest_path="/plain",
        hx_target=None,
        expected_status=200,
        expects_redirect=False,
        expected_body_contains="no-shell",
    ),
    MatrixCase(
        id="13_no_shell_with_target_passes_through",
        scenario="no_shell",
        current_url="http://127.0.0.1:8000/plain",
        dest_path="/plain",
        hx_target=b"#main",
        expected_status=200,
        expects_redirect=False,
        expected_body_contains="no-shell",
    ),
    # --- Robustness: junk HX-Target must never 500 (same-shell, distinct dest) ---
    MatrixCase(
        id="14_junk_hx_target_doctype",
        scenario="full",
        current_url="http://127.0.0.1:8000/a",
        dest_path="/a2",
        hx_target=b"<!DOCTYPE-junk",
        expected_status=200,
        expects_redirect=True,
    ),
    MatrixCase(
        id="15_junk_hx_target_whitespace",
        scenario="full",
        current_url="http://127.0.0.1:8000/a",
        dest_path="/a2",
        hx_target=b"   ",
        expected_status=200,
        expects_redirect=True,
    ),
    # --- Edge: HX-Boosted without HX-Request still treated as boosted ---
    MatrixCase(
        id="16_boosted_without_hx_request",
        scenario="full",
        current_url="http://127.0.0.1:8000/a",
        dest_path="/a2",
        hx_target=b"#" + SITE.encode(),
        expected_status=200,
        expects_redirect=False,
        include_hx_request=False,
        expected_body_contains="in-shell-a-2",
    ),
    # --- Edge: scheme-relative current URL — netloc still matches → resolves ---
    MatrixCase(
        id="17_current_url_scheme_relative",
        scenario="full",
        current_url="//127.0.0.1:8000/a",
        dest_path="/a2",
        hx_target=b"#" + SITE.encode(),
        expected_status=200,
        expects_redirect=False,
        expected_body_contains="in-shell-a-2",
    ),
)


# ---------------------------------------------------------------------------
# Parametrized test
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("case", CASES, ids=lambda c: c.id)
async def test_boosted_navigation_matrix(case: MatrixCase) -> None:
    handler = _make_handler(case.scenario)
    request = _boosted_request(
        path=case.dest_path,
        current_url=case.current_url,
        hx_target=case.hx_target,
        include_hx_request=case.include_hx_request,
        request_type=case.request_type,
    )
    response = await handler(request)

    _assert_boost_invariants(response)

    assert response.status == case.expected_status, (
        f"[{case.id}] expected status {case.expected_status}, got {response.status}"
    )

    redirect = _hx_redirect(response)
    if case.expects_redirect:
        assert redirect is not None, f"[{case.id}] expected HX-Redirect header, none present"
        assert redirect == case.dest_path, (
            f"[{case.id}] HX-Redirect={redirect!r}, expected {case.dest_path!r}"
        )
    else:
        assert redirect is None, f"[{case.id}] unexpected HX-Redirect={redirect!r}"

    if case.expected_body_contains is not None:
        assert case.expected_body_contains in response.text, (
            f"[{case.id}] expected body to contain {case.expected_body_contains!r}, "
            f"got {response.text[:200]!r}"
        )


# ---------------------------------------------------------------------------
# Standalone invariant tests (harder to express as matrix cells)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_plain_get_never_produces_hx_redirect() -> None:
    """Non-boosted GETs don't go through the cross-shell redirect path."""
    handler = _make_handler("full")

    async def _receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    request = Request.from_asgi(
        {
            "type": "http",
            "method": "GET",
            "path": "/a",
            "headers": [],
            "query_string": b"",
            "http_version": "1.1",
            "server": ("127.0.0.1", 8000),
            "client": ("127.0.0.1", 12345),
        },
        _receive,
    )
    response = await handler(request)
    _assert_boost_invariants(response)
    assert response.status == 200
    assert _hx_redirect(response) is None
