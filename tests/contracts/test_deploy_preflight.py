"""Deploy-preflight contract checks (#160)."""

from chirp.config import AppConfig
from chirp.contracts.rules_deploy import (
    check_debug_in_production,
    check_metrics_path_collision,
    check_sentry_sample_rate,
)


class _Route:
    def __init__(self, path: str) -> None:
        self.path = path


class _Router:
    def __init__(self, paths: list[str]) -> None:
        self.routes = [_Route(p) for p in paths]


def test_debug_in_production_errors() -> None:
    cfg = AppConfig(env="production", debug=True, secret_key="x" * 32)
    issues = check_debug_in_production(cfg)
    assert [i.category for i in issues] == ["deploy_debug"]
    assert issues[0].severity.name == "ERROR"


def test_debug_in_development_ok() -> None:
    cfg = AppConfig(env="development", debug=True)
    assert check_debug_in_production(cfg) == []


def test_debug_false_in_production_ok() -> None:
    cfg = AppConfig(env="production", debug=False, secret_key="x" * 32)
    assert check_debug_in_production(cfg) == []


def test_metrics_path_collision_errors() -> None:
    cfg = AppConfig(metrics_enabled=True, metrics_path="/metrics")
    issues = check_metrics_path_collision(cfg, _Router(["/metrics", "/"]))
    assert [i.category for i in issues] == ["deploy_metrics"]


def test_metrics_path_no_collision_ok() -> None:
    cfg = AppConfig(metrics_enabled=True, metrics_path="/metrics")
    assert check_metrics_path_collision(cfg, _Router(["/", "/about"])) == []


def test_metrics_disabled_noop() -> None:
    cfg = AppConfig(metrics_enabled=False, metrics_path="/metrics")
    assert check_metrics_path_collision(cfg, _Router(["/metrics"])) == []


def test_sentry_zero_sample_rate_warns() -> None:
    cfg = AppConfig(sentry_dsn="https://k@sentry.example/1", sentry_traces_sample_rate=0.0)
    issues = check_sentry_sample_rate(cfg)
    assert [i.category for i in issues] == ["deploy_sentry"]
    assert issues[0].severity.name == "WARNING"


def test_sentry_nonzero_rate_ok() -> None:
    cfg = AppConfig(sentry_dsn="https://k@sentry.example/1", sentry_traces_sample_rate=0.1)
    assert check_sentry_sample_rate(cfg) == []


def test_sentry_no_dsn_ok() -> None:
    cfg = AppConfig(sentry_dsn=None, sentry_traces_sample_rate=0.0)
    assert check_sentry_sample_rate(cfg) == []


# ---------------------------------------------------------------------------
# Deploy-posture view (#160): check_hypermedia_surface(deploy=True)
# ---------------------------------------------------------------------------


def test_deploy_posture_escalates_debug_without_mutating_app() -> None:
    """deploy=True runs env-aware rules in production posture, not mutating the app.

    A development app with debug=True is fine in dev but is a production-blocking
    error. Under deploy posture the debug rule fires as an ERROR, while the user's
    real config keeps env='development'.
    """
    from chirp import App, AppConfig
    from chirp.contracts import check_hypermedia_surface

    app = App(AppConfig(env="development", debug=True, secret_key="x" * 32))

    @app.route("/")
    async def index() -> str:  # pragma: no cover - never invoked
        return "ok"

    app.freeze()

    dev_result = check_hypermedia_surface(app)
    assert not [i for i in dev_result.issues if i.category == "deploy_debug"]

    deploy_result = check_hypermedia_surface(app, deploy=True)
    debug_issues = [i for i in deploy_result.issues if i.category == "deploy_debug"]
    assert debug_issues
    assert debug_issues[0].severity.name == "ERROR"

    # The deploy posture never mutates the user's real config.
    assert app.config.env == "development"
