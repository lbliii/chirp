"""Tests for the plugin system."""

import pytest

from chirp import App, AppConfig


class SimplePlugin:
    """A minimal plugin for testing."""

    def __init__(self):
        self.registered = False
        self.prefix = None

    def register(self, app, prefix):
        self.registered = True
        self.prefix = prefix

        @app.route(f"{prefix}/")
        async def plugin_index():
            from chirp.http.response import Response
            return Response("plugin works")


def test_mount_plugin():
    app = App(AppConfig(template_dir="tests/templates"))
    plugin = SimplePlugin()
    app.mount("/blog", plugin)
    assert plugin.registered
    assert plugin.prefix == "/blog"


def test_mount_invalid_plugin():
    app = App(AppConfig(template_dir="tests/templates"))
    with pytest.raises(Exception, match="register"):
        app.mount("/bad", object())


def test_plugin_protocol():
    """SimplePlugin satisfies ChirpPlugin protocol structurally."""
    plugin = SimplePlugin()
    assert hasattr(plugin, "register")
    assert callable(plugin.register)
