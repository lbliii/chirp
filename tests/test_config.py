"""Tests for chirp.config — AppConfig frozen dataclass."""

import os
from pathlib import Path

import pytest

from chirp.config import AppConfig


class TestAppConfig:
    def test_defaults(self) -> None:
        cfg = AppConfig()

        assert cfg.host == "127.0.0.1"
        assert cfg.port == 8000
        assert cfg.debug is False
        assert cfg.secret_key == ""
        assert cfg.template_dir == "templates"
        assert cfg.autoescape is True
        assert cfg.static_dir == "static"
        assert cfg.static_url == "/static"
        assert cfg.sse_heartbeat_interval == 15.0
        assert cfg.mcp_path == "/mcp"
        assert cfg.max_content_length == 16 * 1024 * 1024

    def test_override(self) -> None:
        cfg = AppConfig(host="0.0.0.0", port=3000, debug=True, secret_key="s3cret")

        assert cfg.host == "0.0.0.0"
        assert cfg.port == 3000
        assert cfg.debug is True
        assert cfg.secret_key == "s3cret"

    def test_frozen(self) -> None:
        cfg = AppConfig()

        with pytest.raises(AttributeError):
            cfg.debug = True  # type: ignore[misc]

    def test_template_dir_as_path(self) -> None:
        cfg = AppConfig(template_dir=Path("views"))
        assert cfg.template_dir == Path("views")

    def test_static_dir_none(self) -> None:
        cfg = AppConfig(static_dir=None)
        assert cfg.static_dir is None

    def test_reload_include_default(self) -> None:
        cfg = AppConfig()
        assert cfg.reload_include == (".html", ".css", ".md")

    def test_reload_include_opt_out(self) -> None:
        cfg = AppConfig(reload_include=())
        assert cfg.reload_include == ()

    def test_reload_dirs_default(self) -> None:
        cfg = AppConfig()
        assert cfg.reload_dirs == ()

    def test_reload_include_custom(self) -> None:
        cfg = AppConfig(reload_include=(".html", ".css", ".md"))
        assert cfg.reload_include == (".html", ".css", ".md")

    def test_reload_dirs_custom(self) -> None:
        cfg = AppConfig(reload_dirs=("./templates", "./static"))
        assert cfg.reload_dirs == ("./templates", "./static")

    def test_alpine_defaults(self) -> None:
        cfg = AppConfig()
        assert cfg.alpine is False
        assert cfg.alpine_version == "3.15.8"
        assert cfg.alpine_csp is False

    def test_alpine_enabled(self) -> None:
        cfg = AppConfig(alpine=True)
        assert cfg.alpine is True

    def test_alpine_version_override(self) -> None:
        cfg = AppConfig(alpine=True, alpine_version="3.14.0")
        assert cfg.alpine_version == "3.14.0"

    def test_alpine_csp(self) -> None:
        cfg = AppConfig(alpine=True, alpine_csp=True)
        assert cfg.alpine_csp is True

    def test_from_env_defaults(self) -> None:
        """from_env uses defaults when env is empty."""
        # Clear chirp-related env to avoid leakage from test runner
        env_backup = {k: os.environ.pop(k) for k in list(os.environ) if k.startswith("CHIRP_")}
        try:
            cfg = AppConfig.from_env()
            assert cfg.host == "127.0.0.1"
            assert cfg.port == 8000
            assert cfg.debug is False
            assert cfg.env == "development"
            assert cfg.redis_url is None
            assert cfg.http_timeout == 30.0
            assert cfg.http_retries == 0
            assert cfg.log_format == "auto"
        finally:
            os.environ.update(env_backup)

    def test_from_env_overrides(self) -> None:
        """from_env reads CHIRP_* env vars."""
        env_backup = {k: os.environ.pop(k) for k in list(os.environ) if k.startswith("CHIRP_")}
        try:
            os.environ["CHIRP_HOST"] = "0.0.0.0"
            os.environ["CHIRP_PORT"] = "3000"
            os.environ["CHIRP_DEBUG"] = "true"
            os.environ["CHIRP_SECRET_KEY"] = "from-env"
            os.environ["CHIRP_ENV"] = "production"
            os.environ["CHIRP_REDIS_URL"] = "redis://localhost"
            os.environ["CHIRP_HTTP_TIMEOUT"] = "60"
            os.environ["CHIRP_HTTP_RETRIES"] = "3"
            os.environ["CHIRP_LOG_FORMAT"] = "json"
            cfg = AppConfig.from_env()
            assert cfg.host == "0.0.0.0"
            assert cfg.port == 3000
            assert cfg.debug is True
            assert cfg.secret_key == "from-env"
            assert cfg.env == "production"
            assert cfg.redis_url == "redis://localhost"
            assert cfg.http_timeout == 60.0
            assert cfg.http_retries == 3
            assert cfg.log_format == "json"
        finally:
            os.environ.update(env_backup)

    def test_from_env_invalid_log_format_ignored(self) -> None:
        """Invalid CHIRP_LOG_FORMAT falls back to default."""
        env_backup = {k: os.environ.pop(k) for k in list(os.environ) if k.startswith("CHIRP_")}
        try:
            os.environ["CHIRP_LOG_FORMAT"] = "xml"
            cfg = AppConfig.from_env()
            assert cfg.log_format == "auto"
        finally:
            os.environ.update(env_backup)

    def test_from_env_feature_flags(self) -> None:
        """from_env parses CHIRP_FEATURE_* vars."""
        env_backup = {k: os.environ.pop(k) for k in list(os.environ) if k.startswith("CHIRP_")}
        try:
            os.environ["CHIRP_FEATURE_X"] = "true"
            os.environ["CHIRP_FEATURE_Y"] = "false"
            cfg = AppConfig.from_env()
            assert cfg.feature("x") is True
            assert cfg.feature("y") is False
            assert cfg.feature("z") is False
        finally:
            os.environ.update(env_backup)
