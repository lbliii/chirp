"""python-dotenv / chirp[config] capability proof (#915).

Default installs keep ``chirp[config]`` optional. The specialized
``config-capability`` CI lane installs the extra and sets
``CHIRP_REQUIRE_DOTENV=1`` so package absence fails instead of skipping.
These tests prove ``AppConfig.from_env()`` loads a local ``.env`` file —
no live secrets or network.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from chirp.config import AppConfig
from tests.helpers.config_capability import (
    _REQUIRE_DOTENV_ENV,
    dotenv_package_available,
    ensure_dotenv_package,
)

_ENV_KEYS_TO_CLEAR = ("PORT", "RAILWAY_ENVIRONMENT_ID", "RAILWAY_PUBLIC_DOMAIN")


def _pop_app_env() -> dict[str, str]:
    keys = [
        k for k in os.environ if k.startswith(("CHIRP_", "RAILWAY_")) or k in _ENV_KEYS_TO_CLEAR
    ]
    return {k: os.environ.pop(k) for k in keys}


@pytest.mark.issue(915)
def test_capability_lane_requires_dotenv_package() -> None:
    """config-capability CI must install chirp[config]; default installs stay optional."""
    if os.environ.get(_REQUIRE_DOTENV_ENV) != "1":
        return
    assert dotenv_package_available(), (
        "chirp[config] / python-dotenv missing in config-capability lane"
    )


@pytest.mark.issue(915)
def test_from_env_loads_dotenv_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """When python-dotenv is installed, from_env() loads CHIRP_* from cwd ``.env``."""
    ensure_dotenv_package()
    env_backup = _pop_app_env()
    try:
        (tmp_path / ".env").write_text(
            "CHIRP_DEBUG=true\n"
            "CHIRP_SECRET_KEY=dotenv-capability-secret\n"
            "CHIRP_PORT=4123\n"
            "CHIRP_ENV=staging\n",
            encoding="utf-8",
        )
        monkeypatch.chdir(tmp_path)
        cfg = AppConfig.from_env()
        assert cfg.debug is True
        assert cfg.secret_key == "dotenv-capability-secret"
        assert cfg.port == 4123
        assert cfg.env == "staging"
    finally:
        for k in list(os.environ):
            if k.startswith(("CHIRP_", "RAILWAY_")) or k in _ENV_KEYS_TO_CLEAR:
                del os.environ[k]
        os.environ.update(env_backup)


@pytest.mark.issue(915)
def test_from_env_process_env_wins_over_dotenv(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Existing process env is authoritative; load_dotenv does not override it."""
    ensure_dotenv_package()
    env_backup = _pop_app_env()
    try:
        (tmp_path / ".env").write_text(
            "CHIRP_SECRET_KEY=from-dotenv-file\nCHIRP_DEBUG=true\n",
            encoding="utf-8",
        )
        monkeypatch.chdir(tmp_path)
        os.environ["CHIRP_SECRET_KEY"] = "from-process-env"
        os.environ["CHIRP_DEBUG"] = "false"
        cfg = AppConfig.from_env()
        assert cfg.secret_key == "from-process-env"
        assert cfg.debug is False
    finally:
        for k in list(os.environ):
            if k.startswith(("CHIRP_", "RAILWAY_")) or k in _ENV_KEYS_TO_CLEAR:
                del os.environ[k]
        os.environ.update(env_backup)
