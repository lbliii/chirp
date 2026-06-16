"""E0.1 / E0.2 (#261, #262) — data-pg must not re-enable the GIL on 3.14t."""

import sys
import sysconfig

import pytest


def _free_threaded() -> bool:
    return bool(sysconfig.get_config_var("Py_GIL_DISABLED"))


@pytest.mark.issue(261)
@pytest.mark.issue(262)
@pytest.mark.skipif(not _free_threaded(), reason="requires a free-threaded (3.14t) build")
def test_asyncpg_import_leaves_gil_disabled() -> None:
    pytest.importorskip("asyncpg")
    assert sys._is_gil_enabled() is False
    import asyncpg

    major, minor, *_ = (int(part) for part in asyncpg.__version__.split(".")[:2])
    assert (major, minor) >= (0, 31)
    assert sys._is_gil_enabled() is False


@pytest.mark.issue(262)
@pytest.mark.skipif(not _free_threaded(), reason="requires a free-threaded (3.14t) build")
def test_postgres_backend_import_leaves_gil_disabled() -> None:
    pytest.importorskip("asyncpg")
    assert sys._is_gil_enabled() is False
    import asyncpg

    assert asyncpg is not None
    from chirp.data.drivers import postgres as postgres_driver

    assert postgres_driver.create_pool is not None
    assert sys._is_gil_enabled() is False
