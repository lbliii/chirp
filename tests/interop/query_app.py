"""Public-path Chirp application used by HTTP QUERY interoperability probes."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

from chirp import App, AppConfig, Redirect, Request, Response
from chirp.middleware import CORSConfig, CORSMiddleware

QUERY_MEDIA_TYPE = "application/x-www-form-urlencoded"


@dataclass(frozen=True, slots=True)
class SeenRequest:
    """One request observed after the transport handed it to Chirp."""

    method: str
    body: bytes
    http_version: str


@dataclass(slots=True)
class ProbeState:
    """Per-app observation state; never shared between tests."""

    seen: list[SeenRequest] = field(default_factory=list)
    mutations: int = 0


def _fingerprint(request: Request, body: bytes) -> str:
    digest = hashlib.sha256(body).hexdigest()
    return (
        f'<output data-method="{request.method}" '
        f'data-http-version="{request.http_version}" '
        f'data-length="{len(body)}" data-sha256="{digest}">query-ok</output>'
    )


def make_probe_app(
    *,
    cors_origin: str | None = None,
    cors_allows_query: bool = True,
    chirp_body_limit: int = 16 * 1024 * 1024,
) -> tuple[App, ProbeState]:
    """Build an isolated app that reports method/body transport fidelity as HTML."""
    app = App(
        AppConfig(
            max_request_body_size=chirp_body_limit,
            skip_contract_checks=True,
        )
    )
    state = ProbeState()

    if cors_origin is not None:
        methods = (
            ("GET", "HEAD", "OPTIONS", "QUERY")
            if cors_allows_query
            else (
                "GET",
                "HEAD",
                "OPTIONS",
            )
        )
        app.add_middleware(
            CORSMiddleware(
                CORSConfig(
                    allow_origins=(cors_origin,),
                    allow_methods=methods,
                    allow_headers=("Content-Type",),
                )
            )
        )

    @app.route("/")
    def index() -> Response:
        return Response("<!doctype html><title>QUERY interoperability source</title>")

    @app.route(
        "/query",
        methods=["QUERY"],
        query_media_types=(QUERY_MEDIA_TYPE,),
    )
    async def query(request: Request) -> Response:
        body = await request.body()
        state.seen.append(SeenRequest(request.method, body, request.http_version))
        return Response(_fingerprint(request, body))

    @app.route(
        "/redirect/temporary",
        methods=["QUERY"],
        query_media_types=(QUERY_MEDIA_TYPE,),
    )
    def redirect_temporary() -> Redirect:
        return Redirect("/query", status=307)

    @app.route(
        "/redirect/equivalent",
        methods=["QUERY"],
        query_media_types=(QUERY_MEDIA_TYPE,),
    )
    def redirect_equivalent() -> Redirect:
        return Redirect("/equivalent", status=303)

    @app.route("/equivalent")
    def equivalent(request: Request) -> Response:
        return Response(f'<output data-method="{request.method}">equivalent-get</output>')

    @app.route("/mutation", methods=["POST"])
    def mutation() -> Response:
        state.mutations += 1
        return Response("mutated")

    return app, state
