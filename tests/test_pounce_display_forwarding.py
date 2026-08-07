"""Forward Pounce DisplayConfig through Chirp server launchers (#875)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from pounce.display import DisplayConfig, resolve_display_config

from chirp import App
from chirp.app.server import ServerLauncher
from chirp.app.state import MutableAppState
from chirp.config import AppConfig


def _app_payload(display: DisplayConfig) -> dict[str, str] | None:
    """Mirror Pounce JSON startup ``banner[\"app\"]`` construction."""
    if not display.name:
        return None
    payload: dict[str, str] = {"name": display.name}
    if display.tagline:
        payload["tagline"] = display.tagline
    if display.version:
        payload["version"] = display.version
    return payload


@pytest.mark.issue(875)
class TestDisplayConfigForwarding:
    """Chirp forwards typed DisplayConfig; Pounce owns resolution and signage."""

    @patch("pounce.server.Server")
    def test_dev_forwards_display_unchanged(self, mock_server: MagicMock) -> None:
        from chirp.server.dev import run_dev_server

        display = DisplayConfig(
            name="Chirp Dev",
            tagline="hot reload",
            version="0.1.0",
            lines=("mode: local",),
            signage="minimal",
        )
        app = App(config=AppConfig(debug=True, display=display))

        run_dev_server(app, "127.0.0.1", 8000, display=display)

        config = mock_server.call_args.args[0]
        assert config.display is display

    @patch("pounce.server.Server")
    def test_production_forwards_display_unchanged(self, mock_server: MagicMock) -> None:
        from chirp.server.production import run_production_server

        display = DisplayConfig(
            name="Chirp Prod",
            tagline="production",
            version="1.0.0",
            signage="full",
        )
        app = App(config=AppConfig(debug=False, display=display))

        run_production_server(app, display=display)

        config = mock_server.call_args.args[0]
        assert config.display is display

    @patch("pounce.server.Server")
    def test_unset_display_preserves_pounce_default(self, mock_server: MagicMock) -> None:
        from chirp.server.dev import run_dev_server
        from chirp.server.production import run_production_server

        run_dev_server(App(config=AppConfig(debug=True)), "127.0.0.1", 8000)
        assert mock_server.call_args.args[0].display is None

        mock_server.reset_mock()
        run_production_server(App(config=AppConfig(debug=False)))
        assert mock_server.call_args.args[0].display is None

    @patch("chirp.server.dev.run_dev_server")
    def test_server_launcher_forwards_config_display_dev(self, mock_run: MagicMock) -> None:
        display = DisplayConfig(name="Via Launcher", signage="off")
        config = AppConfig(debug=True, display=display)
        launcher = ServerLauncher(config, MutableAppState())
        app = App(config=config)

        launcher._launch(app, "127.0.0.1", 8000, None)

        assert mock_run.call_args.kwargs["display"] is display

    @patch("chirp.server.production.run_production_server")
    def test_server_launcher_forwards_config_display_production(self, mock_run: MagicMock) -> None:
        display = DisplayConfig(name="Via Launcher Prod", signage="minimal")
        config = AppConfig(debug=False, display=display)
        launcher = ServerLauncher(config, MutableAppState())
        app = App(config=config)

        launcher._launch(app, "0.0.0.0", 8000, None)

        assert mock_run.call_args.kwargs["display"] is display

    @patch("pounce.server.Server")
    def test_caller_display_kwarg_overrides_appconfig(self, mock_server: MagicMock) -> None:
        """Explicit helper ``display=`` wins over AppConfig.display."""
        from chirp.server.production import run_production_server

        config_display = DisplayConfig(name="From Config", signage="full")
        caller_display = DisplayConfig(name="From Caller", signage="minimal")
        app = App(config=AppConfig(debug=False, display=config_display))

        run_production_server(app, display=caller_display)

        assert mock_server.call_args.args[0].display is caller_display

    @pytest.mark.parametrize("signage", ["full", "minimal", "off"])
    @patch("pounce.server.Server")
    def test_signage_modes_forwarded(self, mock_server: MagicMock, signage: str) -> None:
        from chirp.server.dev import run_dev_server

        display = DisplayConfig(name="Signage App", signage=signage)  # type: ignore[arg-type]
        run_dev_server(
            App(config=AppConfig(debug=True)),
            "127.0.0.1",
            8000,
            display=display,
        )
        forwarded = mock_server.call_args.args[0].display
        assert forwarded is display
        assert forwarded.signage == signage
        resolved = resolve_display_config(config_display=forwarded)
        assert resolved.signage == signage

    def test_json_app_identity_from_forwarded_display(self) -> None:
        display = DisplayConfig(
            name="JSON App",
            tagline="typed identity",
            version="2.3.4",
            signage="minimal",
        )
        resolved = resolve_display_config(config_display=display)
        assert _app_payload(resolved) == {
            "name": "JSON App",
            "tagline": "typed identity",
            "version": "2.3.4",
        }

    def test_env_overrides_forwarded_serverconfig_display(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Pounce precedence: environment beats ServerConfig.display."""
        monkeypatch.setenv("POUNCE_APP_NAME", "Env Wins")
        monkeypatch.setenv("POUNCE_SIGNAGE", "off")
        forwarded = DisplayConfig(name="Chirp Config", signage="full")
        resolved = resolve_display_config(config_display=forwarded)
        assert resolved.name == "Env Wins"
        assert resolved.signage == "off"
