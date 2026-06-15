"""E1.1 (#264) — package skeleton imports cleanly and declares free-threading safety."""

import sys
import sysconfig

import pytest

from chirp.data.drivers import _pelt


def _free_threaded() -> bool:
    return bool(sysconfig.get_config_var("Py_GIL_DISABLED"))


@pytest.mark.issue(264)
def test_package_declares_free_threading_safe():
    assert _pelt._Py_mod_gil == 0


@pytest.mark.issue(264)
def test_package_exposes_public_surface():
    for name in (
        "PoolConfig",
        "ConnectionConfig",
        "PeltError",
        "PostgresError",
        "ProtocolError",
        "AuthenticationError",
        "TLSError",
    ):
        assert hasattr(_pelt, name), f"missing public export: {name}"


@pytest.mark.issue(264)
@pytest.mark.skipif(not _free_threaded(), reason="requires a free-threaded (3.14t) build")
def test_import_does_not_re_enable_gil():
    # pelt is pure Python; importing it must never flip the GIL back on under free-threading.
    assert sys._is_gil_enabled() is False
