"""Tests for chirp.app — App lifecycle, registration, and ASGI entry."""

from chirp import App
from chirp.config import AppConfig


class TestAppConfig:
    def test_default_config(self) -> None:
        app = App()
        assert app.config.host == "127.0.0.1"
        assert app.config.port == 8000

    def test_custom_config(self) -> None:
        cfg = AppConfig(host="0.0.0.0", port=3000, debug=True)
        app = App(config=cfg)
        assert app.config.host == "0.0.0.0"
        assert app.config.debug is True
