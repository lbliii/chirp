"""Tests for chirp.config — AppConfig frozen dataclass."""

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
