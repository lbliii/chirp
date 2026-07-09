"""Startup and non-execution contracts for HTTP QUERY (#533)."""

from pathlib import Path

import pytest

from chirp import App, AppConfig, Template
from chirp.contracts import check_hypermedia_surface
from chirp.contracts.rules_query import check_query_contracts
from chirp.contracts.rules_security_stack import is_mutating_route
from chirp.contracts.types import ContractIssue
from chirp.middleware import CORSConfig, CORSMiddleware
from chirp.routing.route import Route
from chirp.routing.router import Router
from chirp.server.speculation_rules import build_speculation_rules_json


def _write_client(tmp_path: Path, script: str) -> None:
    (tmp_path / "client.html").write_text(f"<script>{script}</script>", encoding="utf-8")


def _query_errors(app: App) -> list[ContractIssue]:
    return [
        issue
        for issue in check_hypermedia_surface(app).errors
        if issue.category.startswith("query_")
    ]


@pytest.mark.issue(533)
@pytest.mark.parametrize(
    "script",
    [
        """htmx.ajax("QUERY", "/search", {
            headers: {"Content-Type": "application/json"},
            target: "#results"
        });""",
        """fetch("/search", {
            method: "QUERY",
            headers: {"Content-Type": "application/json"},
            body: "{}"
        });""",
    ],
)
def test_literal_query_clients_match_route_and_media_type(tmp_path: Path, script: str) -> None:
    _write_client(tmp_path, script)
    app = App(AppConfig(template_dir=str(tmp_path)))

    @app.route("/search", methods=["QUERY"], query_media_types=("application/json",))
    def search() -> str:
        return "ok"

    assert _query_errors(app) == []


@pytest.mark.issue(533)
def test_literal_query_client_names_missing_route(tmp_path: Path) -> None:
    _write_client(
        tmp_path,
        'htmx.ajax("QUERY", "/missing", {headers: {"Content-Type": "application/json"}});',
    )
    app = App(AppConfig(template_dir=str(tmp_path)))

    errors = _query_errors(app)

    assert len(errors) == 1
    assert errors[0].category == "query_target"
    assert errors[0].template == "client.html"
    assert "/missing" in errors[0].message
    assert "htmx.ajax" in errors[0].message


@pytest.mark.issue(533)
def test_literal_query_client_names_get_query_mismatch(tmp_path: Path) -> None:
    _write_client(
        tmp_path,
        'fetch("/search", {method: "QUERY", headers: {"Content-Type": "application/json"}});',
    )
    app = App(AppConfig(template_dir=str(tmp_path)))

    @app.route("/search")
    def search() -> str:
        return "ok"

    errors = _query_errors(app)

    assert len(errors) == 1
    assert errors[0].category == "query_method"
    assert errors[0].route == "/search"
    assert "only allows GET" in errors[0].message


@pytest.mark.issue(533)
@pytest.mark.parametrize(
    ("client_options", "expected"),
    [
        ('headers: {"Content-Type": "text/plain"}', "text/plain"),
        ("target: '#results'", "without a literal Content-Type"),
    ],
)
def test_literal_query_client_names_media_mismatch(
    tmp_path: Path,
    client_options: str,
    expected: str,
) -> None:
    _write_client(
        tmp_path,
        f'htmx.ajax("QUERY", "/search", {{{client_options}}});',
    )
    app = App(AppConfig(template_dir=str(tmp_path)))

    @app.route(
        "/search",
        methods=["QUERY"],
        query_media_types=("application/json",),
    )
    def search() -> str:
        return "ok"

    errors = _query_errors(app)

    assert len(errors) == 1
    assert errors[0].category == "query_media_type"
    assert expected in errors[0].message
    assert "application/json" in errors[0].message


@pytest.mark.issue(533)
def test_dynamic_query_headers_are_not_guessed(tmp_path: Path) -> None:
    _write_client(
        tmp_path,
        'fetch("/search", {method: "QUERY", headers: queryHeaders, body: payload});',
    )
    app = App(AppConfig(template_dir=str(tmp_path)))

    @app.route("/search", methods=["QUERY"], query_media_types=("application/json",))
    def search() -> str:
        return "ok"

    assert _query_errors(app) == []


@pytest.mark.issue(533)
@pytest.mark.parametrize(
    "markup",
    [
        '<code>fetch("/missing", {method: "QUERY"})</code>',
        '<script type="application/json">fetch("/missing", {method: "QUERY"})</script>',
        '<script src="client.js">fetch("/missing", {method: "QUERY"})</script>',
        '<script>// fetch("/missing", {method: "QUERY"})</script>',
        '<script>/* fetch("/missing", {method: "QUERY"}) */</script>',
    ],
)
def test_non_executable_query_examples_are_not_clients(tmp_path: Path, markup: str) -> None:
    (tmp_path / "client.html").write_text(markup, encoding="utf-8")
    app = App(AppConfig(template_dir=str(tmp_path)))

    assert _query_errors(app) == []


@pytest.mark.issue(533)
def test_module_script_query_client_is_checked(tmp_path: Path) -> None:
    (tmp_path / "client.html").write_text(
        '<script type="module">fetch("/missing", {method: "QUERY"})</script>',
        encoding="utf-8",
    )
    app = App(AppConfig(template_dir=str(tmp_path)))

    errors = _query_errors(app)

    assert len(errors) == 1
    assert errors[0].category == "query_target"


@pytest.mark.issue(533)
def test_query_cors_requires_query_method_when_origins_are_allowed() -> None:
    app = App(AppConfig())
    app.add_middleware(CORSMiddleware(CORSConfig(allow_origins=("https://example.com",))))

    @app.route("/search", methods=["QUERY"], query_media_types=("application/json",))
    def search() -> str:
        return "ok"

    errors = _query_errors(app)

    assert len(errors) == 1
    assert errors[0].category == "query_cors"
    assert "/search" in errors[0].message
    assert "CORSConfig.allow_methods" in errors[0].message


@pytest.mark.issue(533)
def test_query_cors_requires_content_type_when_method_is_allowed() -> None:
    app = App(AppConfig())
    app.add_middleware(
        CORSMiddleware(
            CORSConfig(
                allow_origins=("https://example.com",),
                allow_methods=("GET", "QUERY"),
            )
        )
    )

    @app.route("/search", methods=["QUERY"], query_media_types=("application/json",))
    def search() -> str:
        return "ok"

    errors = _query_errors(app)

    assert len(errors) == 1
    assert errors[0].category == "query_cors"
    assert errors[0].route == "/search"
    assert "Content-Type" in errors[0].message
    assert "CORSConfig.allow_headers" in errors[0].message


@pytest.mark.issue(533)
def test_query_cors_with_content_type_is_clean() -> None:
    app = App(AppConfig())
    app.add_middleware(
        CORSMiddleware(
            CORSConfig(
                allow_origins=("https://example.com",),
                allow_methods=("GET", "QUERY"),
                allow_headers=("Content-Type",),
            )
        )
    )

    @app.route("/search", methods=["QUERY"], query_media_types=("application/json",))
    def search() -> str:
        return "ok"

    assert _query_errors(app) == []


@pytest.mark.issue(533)
@pytest.mark.parametrize(
    "media_type",
    [
        "application/x-www-form-urlencoded",
        "application/*",
        "multipart/form-data",
        "text/plain;charset=utf-8",
        "text/*",
        "*/*",
    ],
)
def test_query_cors_safelisted_media_does_not_require_content_type_allowance(
    media_type: str,
) -> None:
    app = App(AppConfig())
    app.add_middleware(
        CORSMiddleware(
            CORSConfig(
                allow_origins=("https://example.com",),
                allow_methods=("GET", "QUERY"),
            )
        )
    )

    @app.route("/search", methods=["QUERY"], query_media_types=(media_type,))
    def search() -> str:
        return "ok"

    assert _query_errors(app) == []


@pytest.mark.issue(533)
def test_query_cors_without_allowed_origins_makes_no_cross_origin_claim() -> None:
    app = App(AppConfig())
    app.add_middleware(CORSMiddleware(CORSConfig(allow_methods=("GET", "QUERY"))))

    @app.route("/search", methods=["QUERY"], query_media_types=("application/json",))
    def search() -> str:
        return "ok"

    assert _query_errors(app) == []


@pytest.mark.issue(533)
def test_defensive_rule_rejects_inconsistent_frozen_query_route() -> None:
    def search() -> str:
        return "ok"

    router = Router()
    router.add(Route("/search", search, frozenset({"QUERY"})))
    router.compile()

    errors = check_query_contracts(router, {}, [])

    assert len(errors) == 1
    assert errors[0].severity.value == "error"
    assert errors[0].category == "query_route"
    assert "/search" in errors[0].message
    assert "query_media_types" in errors[0].message


@pytest.mark.issue(533)
def test_query_route_remains_safe_for_security_stack_diagnostics() -> None:
    app = App(AppConfig(env="production", secret_key="test-only-query-contract"))

    @app.route("/search", methods=["QUERY"], query_media_types=("application/json",))
    def search() -> str:
        return "ok"

    check = check_hypermedia_surface(app, deploy=True)
    router = app._runtime_state.router

    assert router is not None
    query_route = next(route for route in router.routes if route.path == "/search")
    assert is_mutating_route(query_route) is False
    assert [issue for issue in check.issues if issue.category == "security_stack"] == []


@pytest.mark.issue(533)
@pytest.mark.asyncio
async def test_query_is_not_executed_by_checks_freeze_speculation_or_autodoc(
    tmp_path: Path,
) -> None:
    from chirp.docs.autodoc import generate_autodoc
    from chirp.freeze import freeze

    (tmp_path / "index.html").write_text(
        "<!DOCTYPE html><html><body>Ready</body></html>",
        encoding="utf-8",
    )
    calls = 0
    app = App(AppConfig(template_dir=str(tmp_path), speculation_rules="eager"))

    @app.route("/")
    def index() -> Template:
        return Template("index.html")

    @app.route("/search", methods=["QUERY"], query_media_types=("application/json",))
    def search() -> str:
        nonlocal calls
        calls += 1
        return "unexpected"

    check_hypermedia_surface(app)
    assert calls == 0

    router = app._runtime_state.router
    assert router is not None
    rules = build_speculation_rules_json(router, "eager")
    assert "/search" not in rules
    assert any(
        page.raw.startswith("# /search") and "Accept-Query" in page.raw
        for page in generate_autodoc(app)
    )
    assert calls == 0

    result = await freeze(app, tmp_path / "output")
    assert result.errors == []
    assert calls == 0
