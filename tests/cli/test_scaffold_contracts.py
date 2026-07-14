"""Scaffolds must pass ``app.check()`` on a clean freeze.

Invariant 1 from ``.cursor/plans/scaffold-modernization.plan.md`` — every
scaffold mode freezes with zero ERROR-severity contract issues.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.cli.conftest import (
    DEPLOYABLE_SCAFFOLD_MODES,
    SCAFFOLD_MODES,
    run_and_parse,
    scaffold,
)

_FREEZE_CHECK_CODE = r"""
import json, sys
sys.path.insert(0, ".")
import app as _app
from chirp.contracts import check_hypermedia_surface

_app.app.freeze()
result = check_hypermedia_surface(_app.app)
errors = [
    {
        "category": i.category,
        "message": i.message,
        "template": i.template,
        "route": i.route,
    }
    for i in result.errors
]
print(json.dumps({
    "ok": result.ok,
    "error_count": len(errors),
    "warning_count": len(result.warnings),
    "errors": errors,
}))
"""


@pytest.mark.parametrize("mode", SCAFFOLD_MODES)
def test_scaffold_freezes_with_no_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mode: str
) -> None:
    project = scaffold(tmp_path, monkeypatch, mode=mode)
    result = run_and_parse(project, _FREEZE_CHECK_CODE)
    assert result.returncode == 0, (
        f"Scaffold '{mode}' subprocess failed:\nstdout: {result.stdout}\nstderr: {result.stderr}"
    )
    assert result.payload.get("ok") is True, (
        f"Scaffold '{mode}' freeze produced ERROR issues: {result.payload.get('errors')}"
    )
    assert result.payload["error_count"] == 0


# Drive the GENERATED app with CHIRP_ENV=production so it reports
# env='production' through its OWN env-aware config (not a substitute
# AppConfig). The scaffold ships no mutating route, so we add a synthetic POST
# route to make the rule fire — but the config and middleware list are the
# generated app's real ones. This proves the env switch (Finding 2) reaches the
# generated config AND that the wired Session/CSRF/SecurityHeaders stack clears
# the env-aware ERROR path — #183's acceptance: minimal + shell pass the
# security_stack contract in production out of the box even once a user adds a
# mutation.
_SECURITY_STACK_PROD_CODE = r"""
import json, sys
sys.path.insert(0, ".")
import app as _app
from chirp.contracts.rules_security_stack import check_security_stack


class _Route:
    methods = {"POST"}


class _Router:
    routes = [_Route()]


_app.app.freeze()
config = _app.app.config
middleware_list = list(_app.app._mutable_state.middleware_list)
issues = check_security_stack(_Router(), config, middleware_list)
print(json.dumps({
    "config_env": config.env,
    "config_debug": config.debug,
    "errors": [i.message for i in issues if i.severity.name == "ERROR"],
    "warnings": [i.message for i in issues if i.severity.name == "WARNING"],
    "middleware": [type(mw).__name__ for mw in middleware_list],
}))
"""


@pytest.mark.parametrize("mode", ["minimal", "shell"])
def test_scaffold_passes_security_stack_in_production(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mode: str
) -> None:
    """#183: generated minimal/shell apps are security_stack-clean in production.

    Drives the generated app with CHIRP_ENV=production so it builds its OWN
    config with env='production' and debug off. The wired
    Session/CSRF/SecurityHeaders middleware means that even when a user promotes
    the app to production and adds a mutating route, the security_stack contract
    emits zero ERRORs (and no SecurityHeaders WARNING).
    """
    project = scaffold(tmp_path, monkeypatch, mode=mode)
    result = run_and_parse(
        project, _SECURITY_STACK_PROD_CODE, extra_env={"CHIRP_ENV": "production"}
    )
    assert result.returncode == 0, (
        f"Scaffold '{mode}' subprocess failed:\nstdout: {result.stdout}\nstderr: {result.stderr}"
    )
    # The env switch must reach the generated config, not just a substitute.
    assert result.payload.get("config_env") == "production", (
        f"Scaffold '{mode}' generated config did not honour CHIRP_ENV=production: "
        f"{result.payload.get('config_env')!r}"
    )
    assert result.payload.get("config_debug") is False, (
        f"Scaffold '{mode}' should default debug off in production: "
        f"{result.payload.get('config_debug')!r}"
    )
    assert result.payload.get("errors") == [], (
        f"Scaffold '{mode}' has security_stack ERRORs in production: {result.payload.get('errors')}"
    )
    # The full stack is wired, so SecurityHeaders never warns either.
    assert result.payload.get("warnings") == [], (
        f"Scaffold '{mode}' has security_stack WARNINGs in production: "
        f"{result.payload.get('warnings')}"
    )
    middleware = result.payload.get("middleware", [])
    assert "SessionMiddleware" in middleware
    assert "CSRFMiddleware" in middleware
    assert "SecurityHeadersMiddleware" in middleware


_RAILWAY_RUNTIME_CODE = r"""
import asyncio, json, sys
sys.path.insert(0, ".")
import app as _app
from chirp.testing import TestClient


async def inspect_runtime():
    async with TestClient(_app.app) as client:
        health_get = await client.get("/health")
        health_head = await client.request("HEAD", "/health")
        ready_get = await client.get("/ready")
        ready_head = await client.request("HEAD", "/ready")
    config = _app.app.config
    print(json.dumps({
        "host": config.host,
        "port": config.port,
        "env": config.env,
        "debug": config.debug,
        "allowed_hosts": config.allowed_hosts,
        "health_get": health_get.status,
        "health_head": health_head.status,
        "ready_get": ready_get.status,
        "ready_head": ready_head.status,
    }))


asyncio.run(inspect_runtime())
"""


@pytest.mark.issue(736)
@pytest.mark.parametrize("mode", DEPLOYABLE_SCAFFOLD_MODES)
def test_scaffold_uses_railway_runtime_contract(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mode: str
) -> None:
    project = scaffold(tmp_path, monkeypatch, mode=mode)
    result = run_and_parse(
        project,
        _RAILWAY_RUNTIME_CODE,
        extra_env={
            "CHIRP_ENV": "production",
            "PORT": "4732",
            "RAILWAY_ENVIRONMENT_ID": "env_test",
            "RAILWAY_PUBLIC_DOMAIN": "launch-board.example.up.railway.app",
        },
    )
    assert result.returncode == 0, (
        f"Scaffold '{mode}' Railway subprocess failed:\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )
    assert result.payload == {
        "host": "0.0.0.0",
        "port": 4732,
        "env": "production",
        "debug": False,
        "allowed_hosts": [
            "launch-board.example.up.railway.app",
            "healthcheck.railway.app",
        ],
        "health_get": 200,
        "health_head": 200,
        "ready_get": 200,
        "ready_head": 200,
    }


# Scaffold the chirp-ui v2 variant, freeze it, and report (a) the generated
# config's CSP posture and (b) every csp_nonce contract issue. #196: the
# chirp-ui scaffold must run the normal Alpine build under a per-request nonce
# CSP (csp_nonce_enabled=True), NOT the @alpinejs/csp build (alpine_csp=True),
# because chirp-ui components use inline Alpine expressions the CSP build forbids.
_CHIRPUI_CSP_NONCE_CODE = r"""
import json, sys
sys.path.insert(0, ".")
import app as _app
from chirp.contracts import check_hypermedia_surface

_app.app.freeze()
config = _app.app.config
result = check_hypermedia_surface(_app.app)
csp_nonce_issues = [
    {"severity": i.severity.name, "message": i.message}
    for i in result.issues
    if i.category == "csp_nonce"
]
print(json.dumps({
    "alpine": config.alpine,
    "alpine_csp": config.alpine_csp,
    "csp_nonce_enabled": config.csp_nonce_enabled,
    "csp_nonce_issues": csp_nonce_issues,
    "ok": result.ok,
}))
"""


def test_chirpui_scaffold_csp_nonce_posture(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """#196: chirp-ui scaffold is csp_nonce-clean under the nonce posture.

    The default ``v2`` variant resolves to chirp-ui in the dev/test env (chirp-ui
    is installed). The generated config must use the normal Alpine build with
    ``csp_nonce_enabled=True`` (auto-wiring CSPNonceMiddleware), not the
    ``@alpinejs/csp`` build, and ``app.check()`` must report no ``csp_nonce``
    issue of any severity.

    The load-bearing regression guard here is the **config shape** below
    (``alpine_csp is False`` + ``csp_nonce_enabled is True``): those fail if the
    scaffold reverts to the broken ``alpine_csp=True`` posture. The
    ``csp_nonce_issues == []`` assertion is a clean-pass check, not a posture
    discriminator — the scaffold hardcodes its config (no ``from_env``), so it
    always reports ``env='development'`` where the rule is silent for *both*
    postures. The genuine old-vs-new rule discrimination (normal Alpine under an
    inline-forbidding CSP ERRORs in production WITHOUT a nonce mechanism, and is
    clean WITH ``csp_nonce_enabled``) is proven at the unit level in
    ``tests/contracts/test_csp_nonce_rule.py`` —
    ``test_fires_in_production_with_forbidding_csp_no_nonce_mechanism`` paired
    with ``test_silent_with_csp_nonce_enabled_config``.
    """
    project = scaffold(tmp_path, monkeypatch, mode="v2")
    result = run_and_parse(project, _CHIRPUI_CSP_NONCE_CODE)
    assert result.returncode == 0, (
        f"chirp-ui scaffold subprocess failed:\nstdout: {result.stdout}\nstderr: {result.stderr}"
    )
    # Alpine is auto-enabled by use_chirp_ui; the CSP build is NOT used.
    assert result.payload.get("alpine") is True
    assert result.payload.get("alpine_csp") is False, (
        "chirp-ui scaffold must not use the @alpinejs/csp build — its inline "
        "Alpine components would silently break in the browser."
    )
    assert result.payload.get("csp_nonce_enabled") is True, (
        "chirp-ui scaffold must enable csp_nonce_enabled to auto-wire "
        "CSPNonceMiddleware for the nonce CSP."
    )
    # Clean-pass check: the nonce mechanism makes every framework inline script
    # nonceable, so the csp_nonce rule returns early. (Clean in dev for both
    # postures — see the docstring; the config-shape asserts above are the
    # posture guard, and the rule unit tests prove the prod discrimination.)
    assert result.payload.get("csp_nonce_issues") == [], (
        f"chirp-ui scaffold has csp_nonce contract issues under the nonce "
        f"posture: {result.payload.get('csp_nonce_issues')}"
    )
    assert result.payload.get("ok") is True
