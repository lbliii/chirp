"""Contract proof for the private multi-worker signal backplane (#699)."""

from __future__ import annotations

import copy

import pytest

from chirp import App, AppConfig
from chirp.contracts import check_hypermedia_surface
from chirp.contracts.types import Severity


def _app(config: AppConfig, *, signals: bool = True) -> App:
    app = App(config)
    if signals:

        @app.signal("status")
        async def status():
            if False:
                yield ""

    app.freeze()
    return app


@pytest.mark.issue(699)
@pytest.mark.parametrize(
    ("env", "workers", "severity"),
    [
        ("production", 0, Severity.ERROR),
        ("production", 2, Severity.ERROR),
        ("staging", 0, Severity.WARNING),
        ("staging", 2, Severity.WARNING),
        ("development", 2, Severity.WARNING),
    ],
)
def test_process_local_multi_worker_matrix(env: str, workers: int, severity: Severity) -> None:
    app = _app(AppConfig(env=env, secret_key="shared", workers=workers))
    issues = [
        issue
        for issue in check_hypermedia_surface(app).issues
        if issue.category == "signal_bus_single_worker"
    ]
    assert len(issues) == 1
    assert issues[0].severity is severity
    rendered = "0 (auto)" if workers == 0 else str(workers)
    assert issues[0].message == (
        f"Signals use a process-local bus with workers={rendered}; realtime updates "
        "cannot reach clients connected to another worker."
    )
    assert issues[0].details == (
        "Set AppConfig(workers=1), or configure AppConfig(redis_url=...) / "
        "CHIRP_REDIS_URL for the private Redis signal backplane and keep signal "
        "source state in a shared store before deploying."
    )


@pytest.mark.issue(699)
def test_safe_worker_and_redis_and_no_signal_shapes_are_clean() -> None:
    safe = _app(AppConfig(env="production", secret_key="shared", workers=1))
    redis = _app(
        AppConfig(
            env="production",
            secret_key="shared",
            workers=4,
            redis_url="redis://private.invalid/0",
        )
    )
    empty = _app(
        AppConfig(env="production", secret_key="shared", workers=4),
        signals=False,
    )
    for app in (safe, redis, empty):
        assert not [
            issue
            for issue in check_hypermedia_surface(app).issues
            if issue.category == "signal_bus_single_worker"
        ]


@pytest.mark.issue(699)
def test_deploy_posture_is_tighten_only_and_does_not_mutate_config() -> None:
    app = _app(AppConfig(env="development", workers=0))
    before = copy.copy(app.config)
    result = check_hypermedia_surface(app, deploy=True)
    issues = [i for i in result.issues if i.category == "signal_bus_single_worker"]
    assert len(issues) == 1
    assert issues[0].severity is Severity.ERROR
    assert app.config == before
