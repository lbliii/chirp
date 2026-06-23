"""E0.1 / E0.2 (#261, #262) — data-pg must not re-enable the GIL on 3.14t."""

import sys
import sysconfig

import pytest


def _free_threaded() -> bool:
    return bool(sysconfig.get_config_var("Py_GIL_DISABLED"))


@pytest.mark.issue(261)
@pytest.mark.issue(262)
@pytest.mark.skipif(not _free_threaded(), reason="requires a free-threaded (3.14t) build")
def test_pelt_import_leaves_gil_disabled() -> None:
    assert sys._is_gil_enabled() is False
    import chirp.data.drivers._pelt as pelt

    assert pelt is not None
    assert sys._is_gil_enabled() is False


@pytest.mark.issue(262)
@pytest.mark.skipif(not _free_threaded(), reason="requires a free-threaded (3.14t) build")
def test_postgres_backend_import_leaves_gil_disabled() -> None:
    assert sys._is_gil_enabled() is False
    from chirp.data.drivers import postgres as postgres_driver

    assert postgres_driver.create_pool is not None
    assert sys._is_gil_enabled() is False
