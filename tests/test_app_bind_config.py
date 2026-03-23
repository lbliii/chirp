"""Tests for ``App.bind_config`` — config must mirror into internal subsystems."""

from dataclasses import replace

from chirp import App
from chirp.config import AppConfig


def test_bind_config_syncs_internal_references() -> None:
    """``app.config = ...`` alone is insufficient; ``bind_config`` updates compiler/runtime."""
    app = App(config=AppConfig(debug=False))
    new_cfg = replace(app.config, debug=True, alpine=True)
    app.bind_config(new_cfg)
    assert app.config is new_cfg
    assert app._compiler._config is new_cfg
    assert app._runtime._config is new_cfg
    assert app._server._config is new_cfg
    assert app._lifecycle._config is new_cfg
    assert app._contract_checks._config is new_cfg
