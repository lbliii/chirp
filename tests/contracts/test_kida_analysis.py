"""Kida 0.9 static analysis surfaced through app.check()."""

from chirp import App
from chirp.config import AppConfig
from chirp.contracts import Severity, check_hypermedia_surface


def test_safe_filter_without_reason_surfaces_escape_warning(tmp_path):
    (tmp_path / "page.html").write_text("{{ html | safe }}")
    app = App(AppConfig(template_dir=str(tmp_path)))

    @app.route("/")
    async def home():
        return "ok"

    result = check_hypermedia_surface(app)

    issues = [i for i in result.issues if i.category == "template_escape"]
    assert len(issues) == 1
    assert issues[0].severity == Severity.WARNING
    assert "|safe marks output as trusted markup" in issues[0].message
    assert issues[0].template == "page.html"
    assert "K-ESC-002" in (issues[0].details or "")
    assert 'safe(reason="...")' in (issues[0].details or "")


def test_sensitive_context_path_surfaces_privacy_warning(tmp_path):
    (tmp_path / "page.html").write_text("{{ user.password }}")
    app = App(AppConfig(template_dir=str(tmp_path)))

    @app.route("/")
    async def home():
        return "ok"

    result = check_hypermedia_surface(app)

    issues = [i for i in result.issues if i.category == "template_privacy"]
    assert len(issues) == 1
    assert issues[0].severity == Severity.WARNING
    assert "user.password" in issues[0].message
    assert issues[0].template == "page.html"
    assert "K-PRI-001" in (issues[0].details or "")


def test_dotted_context_contract_reports_missing_path(tmp_path):
    (tmp_path / "page.html").write_text("{{ page.title }} {{ user.name }}")
    app = App(AppConfig(template_dir=str(tmp_path)))
    app.set_contract_check_data(
        "template_context_contracts",
        {"page.html": {"provided": {"page.title"}}},
    )

    @app.route("/")
    async def home():
        return "ok"

    result = check_hypermedia_surface(app)

    issues = [i for i in result.issues if i.category == "template_context"]
    assert len(issues) == 1
    assert issues[0].severity == Severity.ERROR
    assert "user.name" in issues[0].message
    assert issues[0].template == "page.html"
    assert "K-CTX-001" in (issues[0].details or "")


def test_dotted_context_contract_allows_optional_paths(tmp_path):
    (tmp_path / "page.html").write_text("{{ page.title }} {{ user.name }}")
    app = App(AppConfig(template_dir=str(tmp_path)))
    app.set_contract_check_data(
        "template_context_contracts",
        {
            "page.html": {
                "provided": {"page.title"},
                "optional": {"user.name"},
            }
        },
    )

    @app.route("/")
    async def home():
        return "ok"

    result = check_hypermedia_surface(app)

    assert [i for i in result.issues if i.category == "template_context"] == []


def test_literal_attributes_feed_hx_target_validation(tmp_path):
    (tmp_path / "page.html").write_text('<button hx-target="#missing">Save</button>')
    app = App(AppConfig(template_dir=str(tmp_path)))

    @app.route("/")
    async def home():
        return "ok"

    result = check_hypermedia_surface(app)

    issues = [i for i in result.issues if i.category == "hx-target"]
    assert len(issues) == 1
    assert issues[0].severity == Severity.WARNING
    assert "missing" in issues[0].message
