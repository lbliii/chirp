"""End-to-end WebMCP startup diagnostics and coverage for issue #575."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

import pytest

from chirp import App, AppConfig, WebMCPForm
from chirp.contracts import FormContract, check_hypermedia_surface, contract
from chirp.contracts.diff import diff_contract_dicts
from chirp.contracts.serialize import result_to_dict
from chirp.middleware.csrf import CSRFMiddleware
from chirp.middleware.sessions import SessionConfig, SessionMiddleware
from chirp.server.terminal_checks import format_check_result

pytestmark = pytest.mark.issue(575)


@dataclass(frozen=True, slots=True)
class SearchForm:
    query: str = field(
        metadata={
            "webmcp_control": "search",
            "webmcp_description": "Words to search for",
            "webmcp_min_length": 2,
        }
    )
    limit: int = field(
        default=10,
        metadata={
            "webmcp_control": "number",
            "webmcp_description": "Maximum result count",
            "webmcp_min": 1,
            "webmcp_max": 50,
        },
    )


VALID_TEMPLATE = """
{% block search_form %}
<form method="post" action="/search"{{ webmcp_form_attrs("search.run") }}>
  {{ csrf_field() }}
  <input{{ webmcp_control_attrs("search.run", "query") }}>
  <input{{ webmcp_control_attrs("search.run", "limit") }}>
  <button type="submit">Search</button>
</form>
{% end %}
"""


def _checked_app(
    tmp_path: Path,
    *,
    template: str = VALID_TEMPLATE,
    declaration: object = WebMCPForm("search.run", "Search the catalog"),
    datacls: type = SearchForm,
    block: str | None = "search_form",
    csrf: bool = True,
    skip_contract_checks: bool = True,
    path: str = "/search",
    method: str = "POST",
):
    tmp_path.joinpath("search.html").write_text(template, encoding="utf-8")
    app = App(
        AppConfig(
            template_dir=tmp_path,
            skip_contract_checks=skip_contract_checks,
            debug=not skip_contract_checks,
        )
    )
    if csrf:
        app.add_middleware(SessionMiddleware(SessionConfig(secret_key="test-secret")))
        app.add_middleware(CSRFMiddleware())

    @app.route(path, methods=[method])
    @contract(
        form=FormContract(
            datacls,
            "search.html",
            block,
            webmcp=cast(Any, declaration),
        )
    )
    def search() -> str:
        return "ok"

    app.freeze()
    return app, check_hypermedia_surface(app)


def _webmcp_errors(result):
    return [issue for issue in result.errors if issue.category == "webmcp"]


def test_valid_projection_has_no_findings_and_reports_coverage(tmp_path: Path) -> None:
    _, result = _checked_app(tmp_path)

    assert _webmcp_errors(result) == []
    assert result.coverage.webmcp_projections_declared == 1
    assert result.coverage.webmcp_projections_compiled == 1
    assert result.coverage.webmcp_parameters_declared == 2

    default_payload = result_to_dict(result)
    coverage_payload = result_to_dict(result, include_coverage=True)
    assert "coverage" not in default_payload
    assert coverage_payload["coverage"]["webmcp_projections_compiled"] == 1
    assert "WebMCP projections: 1/1 compiled (2 parameters)" in format_check_result(
        result, color=False, show_coverage=True
    )


@pytest.mark.parametrize(
    ("declaration", "message"),
    [
        (WebMCPForm("", "Search"), "tool_name must start"),
        (WebMCPForm("search.run", ""), "requires a non-empty description"),
        (WebMCPForm("search.run", "Search", autosubmit=True), "cannot enable autosubmit"),
        ("not-a-projection", "must be a WebMCPForm"),
    ],
)
def test_compile_failures_become_structured_errors(
    tmp_path: Path,
    declaration: object,
    message: str,
) -> None:
    _, result = _checked_app(tmp_path, declaration=declaration)

    errors = _webmcp_errors(result)
    assert len(errors) == 1
    assert message in errors[0].message
    assert "route '/search'" in errors[0].message
    assert "template 'search.html' block 'search_form'" in errors[0].message
    assert errors[0].severity.value == "error"
    payload = result_to_dict(result, include_coverage=True)
    assert payload["issues"][0]["category"] == "webmcp"
    assert payload["coverage"]["webmcp_projections_compiled"] == 0


def test_unsupported_control_is_actionable_structured_error(tmp_path: Path) -> None:
    @dataclass
    class UploadForm:
        payload: str = field(
            metadata={
                "webmcp_control": "file",
                "webmcp_description": "Upload payload",
            }
        )

    _, result = _checked_app(tmp_path, datacls=UploadForm)

    error = _webmcp_errors(result)[0]
    assert "UploadForm.payload" in error.message
    assert "unsupported control 'file'" in error.message
    assert "Supported controls" in error.message


def test_duplicate_operation_identity_names_both_routes(tmp_path: Path) -> None:
    tmp_path.joinpath("duplicate.html").write_text(VALID_TEMPLATE, encoding="utf-8")
    duplicate = App(AppConfig(template_dir=tmp_path, skip_contract_checks=True))
    duplicate.add_middleware(SessionMiddleware(SessionConfig(secret_key="test-secret")))
    duplicate.add_middleware(CSRFMiddleware())
    for path in ("/search", "/search-again"):

        def handler() -> str:
            return "ok"

        handler = contract(
            form=FormContract(
                SearchForm,
                "search.html",
                "search_form",
                webmcp=WebMCPForm("search.run", "Search"),
            )
        )(handler)
        duplicate.route(path, methods=["POST"])(handler)
    duplicate.freeze()
    result = check_hypermedia_surface(duplicate)

    error = next(issue for issue in _webmcp_errors(result) if "Duplicate" in issue.message)
    assert "'/search'" in error.message
    assert "'/search-again'" in error.message


def test_duplicate_descriptions_name_both_operation_sources(tmp_path: Path) -> None:
    duplicate = App(AppConfig(template_dir=tmp_path, skip_contract_checks=True))
    duplicate.add_middleware(SessionMiddleware(SessionConfig(secret_key="test-secret")))
    duplicate.add_middleware(CSRFMiddleware())
    for suffix in ("one", "two"):
        operation = f"search.{suffix}"
        route_path = f"/search-{suffix}"
        template_name = f"search-{suffix}.html"
        tmp_path.joinpath(template_name).write_text(
            VALID_TEMPLATE.replace("search.run", operation).replace("/search", route_path),
            encoding="utf-8",
        )

        def handler() -> str:
            return "ok"

        handler = contract(
            form=FormContract(
                SearchForm,
                template_name,
                "search_form",
                webmcp=WebMCPForm(operation, "Search the catalog"),
            )
        )(handler)
        duplicate.route(route_path, methods=["POST"])(handler)
    duplicate.freeze()
    result = check_hypermedia_surface(duplicate)

    error = next(
        issue for issue in _webmcp_errors(result) if "Duplicate WebMCP description" in issue.message
    )
    assert "search.one" in error.message
    assert "search.two" in error.message
    assert "search-one.html" in error.message
    assert "search-two.html" in error.message


@pytest.mark.parametrize(
    ("template", "message"),
    [
        (
            VALID_TEMPLATE.replace("{% block search_form %}", "{% block other %}"),
            "missing named block",
        ),
        (VALID_TEMPLATE.replace(' action="/search"', ""), "no literal fallback form action"),
        (
            VALID_TEMPLATE.replace(' action="/search"', ' action="/missing"'),
            "does not match route path",
        ),
        (VALID_TEMPLATE.replace(' method="post"', ' method="get"'), "does not match route methods"),
        (
            VALID_TEMPLATE.replace('<button type="submit">Search</button>', ""),
            "no native submit control",
        ),
        (
            VALID_TEMPLATE.replace(
                '{{ webmcp_control_attrs("search.run", "query") }}',
                '{{ webmcp_control_attrs("other.run", "wrong") }}',
            ),
            "does not project form control 'query'",
        ),
        (
            VALID_TEMPLATE.replace(
                '{{ webmcp_form_attrs("search.run") }}',
                '{{ webmcp_form_attrs("other.run") }}',
            ),
            "must render exactly one real <form>",
        ),
        (VALID_TEMPLATE.replace("{{ csrf_field() }}", ""), "omits the CSRF field"),
        (
            VALID_TEMPLATE.replace(
                '{{ webmcp_form_attrs("search.run") }}',
                '{{ webmcp_form_attrs("search.run") }} toolname="raw"',
            ),
            "mixes raw WebMCP attributes",
        ),
        (
            VALID_TEMPLATE.replace(
                '<input{{ webmcp_control_attrs("search.run", "query") }}>',
                '<input name="wrong"{{ webmcp_control_attrs("search.run", "query") }}>',
            ),
            "mixes compiled control metadata with literal 'name'",
        ),
    ],
)
def test_template_and_fallback_drift_fails_loudly(
    tmp_path: Path,
    template: str,
    message: str,
) -> None:
    _, result = _checked_app(tmp_path, template=template)
    assert any(message in issue.message for issue in _webmcp_errors(result))


def test_mutation_requires_csrf_security_wiring(tmp_path: Path) -> None:
    _, result = _checked_app(tmp_path, csrf=False)

    error = next(issue for issue in _webmcp_errors(result) if "CSRFMiddleware" in issue.message)
    assert error.route == "/search"
    assert "SessionMiddleware then CSRFMiddleware" in (error.details or "")


def test_raw_or_undeclared_preview_markup_is_rejected(tmp_path: Path) -> None:
    source = """
    <form method="post" action="/search" toolname="raw.search" tooldescription="Raw">
      <input name="query" toolparamdescription="Query">
      <button type="submit">Search</button>
    </form>
    {{ webmcp_form_attrs("missing.run") }}
    """
    tmp_path.joinpath("raw.html").write_text(source, encoding="utf-8")
    app = App(AppConfig(template_dir=tmp_path, skip_contract_checks=True))

    @app.route("/search", methods=["POST"])
    def search() -> str:
        return "ok"

    app.freeze()
    result = check_hypermedia_surface(app)
    messages = [issue.message for issue in _webmcp_errors(result)]
    assert any("raw toolname markup" in message for message in messages)
    assert any("undeclared WebMCP operation 'missing.run'" in message for message in messages)


def test_contract_diff_reports_webmcp_coverage_change(tmp_path: Path) -> None:
    _, result = _checked_app(tmp_path)
    current = result_to_dict(result, include_coverage=True)
    baseline = {**current, "coverage": {}}

    diff = diff_contract_dicts(baseline, current)

    names = {item["name"] for item in diff.coverage_changes}
    assert "webmcp_projections_declared" in names
    assert "webmcp_projections_compiled" in names
    assert "webmcp_parameters_declared" in names
    assert any("coverage webmcp_projections_compiled" in line for line in diff.summary_lines())


def test_malformed_projection_blocks_normal_debug_startup(tmp_path: Path) -> None:
    with pytest.raises(SystemExit) as exc_info:
        _checked_app(
            tmp_path,
            declaration=WebMCPForm("", "Search"),
            skip_contract_checks=False,
        )

    assert exc_info.value.code == 1
