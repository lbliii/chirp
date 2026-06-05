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
    app = App(AppConfig(skip_contract_checks=True, template_dir=str(tmp_path), debug=True, env="production", secret_key="x" * 32))

    @app.route("/")
    def index():
        return "ok"

    assert "deploy_debug" in _categories(app)


def test_deploy_metrics_collision_fires(tmp_path) -> None:
    (tmp_path / "index.html").write_text("<div id='x'></div>", encoding="utf-8")
    app = App(AppConfig(skip_contract_checks=True, template_dir=str(tmp_path), metrics_enabled=True, metrics_path="/metrics"))

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
