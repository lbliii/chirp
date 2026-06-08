"""End-to-end app.check() coverage for the new contract categories (#160/#152/#161).

The per-rule unit tests use stub routers; these prove the rules are actually
WIRED into check_hypermedia_surface and fire against a REAL App + Router (so a
wiring regression or a router-shape change cannot stay green silently).
"""

from chirp import App
from chirp.config import AppConfig
from chirp.contracts import check_hypermedia_surface
from chirp.templating.returns import Fragment


def _categories(app: App) -> set[str]:
    return {issue.category for issue in check_hypermedia_surface(app).issues}


def test_deploy_debug_fires_in_production(tmp_path) -> None:
    (tmp_path / "index.html").write_text("<div id='x'></div>", encoding="utf-8")
    app = App(
        AppConfig(
            skip_contract_checks=True,
            template_dir=str(tmp_path),
            debug=True,
            env="production",
            secret_key="x" * 32,
        )
    )

    @app.route("/")
    def index():
        return "ok"

    assert "deploy_debug" in _categories(app)


def test_deploy_metrics_collision_fires(tmp_path) -> None:
    (tmp_path / "index.html").write_text("<div id='x'></div>", encoding="utf-8")
    app = App(
        AppConfig(
            skip_contract_checks=True,
            template_dir=str(tmp_path),
            metrics_enabled=True,
            metrics_path="/metrics",
        )
    )

    @app.route("/metrics")
    def metrics_route():
        return "ok"

    assert "deploy_metrics" in _categories(app)


def test_deploy_sentry_zero_rate_fires(tmp_path) -> None:
    (tmp_path / "index.html").write_text("<div id='x'></div>", encoding="utf-8")
    app = App(
        AppConfig(
            skip_contract_checks=True,
            template_dir=str(tmp_path),
            sentry_dsn="https://k@sentry.example/1",
            sentry_traces_sample_rate=0.0,
        )
    )

    @app.route("/")
    def index():
        return "ok"

    assert "deploy_sentry" in _categories(app)


def test_nojs_floor_fires_for_htmx_only_mutation(tmp_path) -> None:
    (tmp_path / "index.html").write_text("<div id='x'></div>", encoding="utf-8")
    app = App(AppConfig(template_dir=str(tmp_path)))

    @app.route("/save", methods=["POST"])
    def save(request):
        return Fragment("index.html", "x")

    assert "nojs_floor" in _categories(app)


def test_security_stack_fires_in_production(tmp_path) -> None:
    (tmp_path / "index.html").write_text("<div id='x'></div>", encoding="utf-8")
    app = App(
        AppConfig(
            skip_contract_checks=True,
            template_dir=str(tmp_path),
            env="production",
            secret_key="x" * 32,
        )
    )

    @app.route("/save", methods=["POST"])
    def save(request):
        return Fragment("index.html", "x")

    issues = check_hypermedia_surface(app).issues
    security = [i for i in issues if i.category == "security_stack"]
    assert security, "security_stack did not fire for a production mutating route"
    # CSRF/Session missing in production must be an ERROR.
    assert any(i.severity.name == "ERROR" for i in security)


def test_security_stack_silent_in_development(tmp_path) -> None:
    (tmp_path / "index.html").write_text("<div id='x'></div>", encoding="utf-8")
    app = App(
        AppConfig(
            skip_contract_checks=True,
            template_dir=str(tmp_path),
            env="development",
        )
    )

    @app.route("/save", methods=["POST"])
    def save(request):
        return Fragment("index.html", "x")

    issues = check_hypermedia_surface(app).issues
    security = [i for i in issues if i.category == "security_stack"]
    # SecurityHeaders WARNING may appear; no ERROR in development.
    assert not [i for i in security if i.severity.name == "ERROR"]


def test_security_stack_fully_wired_is_clean(tmp_path) -> None:
    from chirp.middleware.csrf import CSRFConfig, CSRFMiddleware
    from chirp.middleware.security_headers import SecurityHeadersMiddleware
    from chirp.middleware.sessions import SessionConfig, SessionMiddleware

    (tmp_path / "index.html").write_text("<div id='x'></div>", encoding="utf-8")
    secret = "x" * 32
    app = App(
        AppConfig(
            skip_contract_checks=True,
            template_dir=str(tmp_path),
            env="production",
            secret_key=secret,
        )
    )
    app.add_middleware(SessionMiddleware(SessionConfig(secret_key=secret)))
    app.add_middleware(CSRFMiddleware(CSRFConfig()))
    app.add_middleware(SecurityHeadersMiddleware())

    @app.route("/save", methods=["POST"])
    def save(request):
        return Fragment("index.html", "x")

    issues = check_hypermedia_surface(app).issues
    assert [i for i in issues if i.category == "security_stack"] == []


def _write_get_only_action_page(pages_dir) -> None:
    """A filesystem page that declares only get() but ships _actions.py.

    This is the canonical false-negative the broadened mutating-route
    definition closes: the page mutates state via POST-to-self on the _action
    field, yet the router route is method-GET. Only the discovered PageRoute's
    `actions` reveals it as mutating.
    """
    pages_dir.mkdir()
    (pages_dir / "_layout.html").write_text(
        "<!doctype html><html><body>{% block content %}{% end %}</body></html>",
        encoding="utf-8",
    )
    (pages_dir / "page.py").write_text(
        "from chirp import Template\n\n\ndef get():\n    return Template('page.html')\n",
        encoding="utf-8",
    )
    (pages_dir / "page.html").write_text(
        "{% extends '_layout.html' %}{% block content %}<div id='x'>hi</div>{% end %}",
        encoding="utf-8",
    )
    (pages_dir / "_actions.py").write_text(
        "from chirp import Redirect\n"
        "from chirp.pages.actions import action\n\n\n"
        '@action("save")\n'
        "def save():\n"
        "    return Redirect('/')\n",
        encoding="utf-8",
    )


def test_security_stack_fires_for_get_only_action_page_in_production(tmp_path) -> None:
    """A GET-only filesystem page backed by _actions.py is a mutating surface.

    Proves the discovered_routes wiring: the router route is method-GET, so the
    method-only definition would miss it; the contract must still flag it as a
    production ERROR because the page mutates via _actions.py POST-to-self.
    """
    pages_dir = tmp_path / "pages"
    _write_get_only_action_page(pages_dir)
    app = App(
        AppConfig(
            skip_contract_checks=True,
            template_dir=str(pages_dir),
            env="production",
            secret_key="x" * 32,
        )
    )
    app.mount_pages(str(pages_dir))

    issues = check_hypermedia_surface(app).issues
    security = [i for i in issues if i.category == "security_stack"]
    assert security, "security_stack did not fire for a GET-only _actions.py page"
    protection = [
        i for i in security if "CSRFMiddleware" in i.message or "SessionMiddleware" in i.message
    ]
    assert protection, "CSRF/Session protection issue missing for form-action page"
    assert protection[0].severity.name == "ERROR"


def test_security_stack_silent_for_get_only_action_page_in_development(tmp_path) -> None:
    """The same page in development emits no CSRF/Session ERROR (dev stays clean)."""
    pages_dir = tmp_path / "pages"
    _write_get_only_action_page(pages_dir)
    app = App(
        AppConfig(
            skip_contract_checks=True,
            template_dir=str(pages_dir),
            env="development",
        )
    )
    app.mount_pages(str(pages_dir))

    issues = check_hypermedia_surface(app).issues
    security = [i for i in issues if i.category == "security_stack"]
    assert not [i for i in security if i.severity.name == "ERROR"]


def test_i18n_missing_key_fires(tmp_path) -> None:
    templates = tmp_path / "templates"
    templates.mkdir()
    (templates / "index.html").write_text('<h1>{{ t("missing.key") }}</h1>', encoding="utf-8")
    locales = tmp_path / "locales"
    locales.mkdir()
    (locales / "en.json").write_text('{"present": "Hi"}', encoding="utf-8")

    app = App(
        AppConfig(
            skip_contract_checks=True,
            template_dir=str(templates),
            i18n_enabled=True,
            i18n_directory=str(locales),
            i18n_supported_locales=("en",),
        )
    )

    @app.route("/")
    def index():
        return "ok"

    assert "i18n_missing_key" in _categories(app)
