"""Focused repair and redaction guarantees for contract diagnostics."""

from chirp import App, AppConfig
from chirp.contracts import CheckResult, check_hypermedia_surface
from chirp.contracts.serialize import issue_to_dict


def test_plugin_failure_has_compact_terminal_and_json_repair_guidance(tmp_path) -> None:
    app = App(AppConfig(template_dir=str(tmp_path)))

    @app.route("/")
    def index():
        return "ok"

    def fails(snapshot, result: CheckResult) -> None:
        raise RuntimeError("token=private-value at /Users/example/private-app")

    app.register_contract_check(fails)
    result = check_hypermedia_surface(app)
    issue = next(issue for issue in result.issues if issue.category == "plugin_check_error")
    assert issue.details is not None
    payload = issue_to_dict(issue)
    assert payload["details"] == issue.details
    assert "Repair surface: custom check 'fails'" in issue.details
    assert issue.details in result.summary()
    rendered = f"{issue.message}\n{issue.details}"
    assert "RuntimeError" in rendered
    assert "private-value" not in rendered
    assert "/Users/example/private-app" not in rendered


def test_route_target_and_method_errors_name_their_local_repair_surface(tmp_path) -> None:
    (tmp_path / "page.html").write_text(
        '<button hx-post="/save"></button><button hx-get="/missing"></button>',
        encoding="utf-8",
    )
    app = App(AppConfig(template_dir=str(tmp_path)))

    @app.route("/")
    def index():
        return "ok"

    @app.route("/save")
    def save():
        return "ok"

    issues = {issue.category: issue for issue in check_hypermedia_surface(app).issues}
    assert issues["method"].details == (
        "Change 'hx-post' in this template or add POST to the registered route '/save'."
    )
    assert issues["target"].details == (
        "Register '/missing' as a route, or correct 'hx-get' in this template."
    )
