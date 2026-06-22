"""Tests for the plugin system."""

import pytest

from chirp import App, AppConfig
from chirp.contracts import Severity, check_hypermedia_surface


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


class RaisingPlugin:
    """A plugin whose register() raises — should be quarantined, not abort boot."""

    def register(self, app, prefix):
        raise RuntimeError("boom from plugin register")


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


@pytest.mark.issue(382)
def test_broken_plugin_is_quarantined(caplog):
    """A plugin whose register() raises is quarantined: app boots, other plugins
    register, and app.check() surfaces a plugin_quarantine ERROR (#382)."""
    import logging

    app = App(AppConfig(template_dir="tests/templates"))
    raising = RaisingPlugin()
    good = SimplePlugin()

    # (a) mount() of a raising plugin does NOT propagate — boot stays alive.
    with caplog.at_level(logging.WARNING, logger="chirp"):
        app.mount("/broken", raising)
    # A non-fatal WARNING is logged at mount time (signal exists even if checks
    # are skipped) naming the prefix and original error.
    assert any(
        rec.levelno == logging.WARNING
        and "/broken" in rec.getMessage()
        and "boom from plugin register" in rec.getMessage()
        for rec in caplog.records
    )

    # (b) A subsequent good plugin still registers and its route exists.
    app.mount("/blog", good)
    assert good.registered is True
    assert good.prefix == "/blog"

    app.freeze()
    route_paths = {r.path for r in app._runtime_state.router.routes}
    assert "/blog/" in route_paths
    assert "/broken/" not in route_paths

    # (c) app.check() yields a plugin_quarantine ERROR naming prefix + error.
    result = check_hypermedia_surface(app)
    quarantine_issues = [i for i in result.issues if i.category == "plugin_quarantine"]
    assert len(quarantine_issues) == 1
    issue = quarantine_issues[0]
    assert issue.severity == Severity.ERROR
    assert "/broken" in issue.message
    assert "boom from plugin register" in issue.message


def test_missing_register_stays_fail_loud():
    """A non-plugin object (no callable register) is a fail-loud ConfigurationError,
    NOT a quarantine — that is a call-site typo, not a runtime plugin fault (#382)."""
    from chirp.errors import ConfigurationError

    app = App(AppConfig(template_dir="tests/templates"))
    with pytest.raises(ConfigurationError, match="register"):
        app.mount("/bad", object())
    # No quarantine recorded for the fail-loud path.
    assert app._mutable_state.plugin_quarantines == []
