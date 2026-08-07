"""Stack free-threading glue proof for issue #944.

Chirp app → Pelt ``Pool`` checkout → Kida ``Template`` render → Pounce
``TestServer``, asserted under a free-threaded build with the GIL disabled.
"""

from __future__ import annotations

import sys
import sysconfig
from pathlib import Path
from typing import Any, cast

import httpx
import pytest
from pounce.testing import TestServer

from chirp import App, AppConfig, Template
from chirp.data.drivers._pelt import _runtime
from chirp.data.drivers._pelt.pool import Pool


def _nogil_runtime() -> bool:
    return bool(sysconfig.get_config_var("Py_GIL_DISABLED")) and sys._is_gil_enabled() is False


class _ProbeConnection:
    """Pool ownership probe — no PostgreSQL wire I/O."""

    def __init__(self, identifier: int) -> None:
        self.identifier = identifier
        self.reset_count = 0

    async def reset_if_needed(self) -> None:
        self.reset_count += 1

    async def close(self) -> None:
        return None


@pytest.mark.issue(944)
@pytest.mark.skipif(
    not _nogil_runtime(),
    reason="requires a free-threaded build with PYTHON_GIL=0 (GIL disabled)",
)
def test_chirp_pelt_kida_pounce_stack_under_nogil(tmp_path: Path) -> None:
    """Acceptance #944: stack path stays coherent with the GIL off."""
    assert sys._is_gil_enabled() is False
    assert _runtime.is_free_threading_enabled() is True

    (tmp_path / "page.html").write_text(
        '<!doctype html><title>{{ title }}</title><p data-conn="{{ conn_id }}">{{ title }}</p>\n',
        encoding="utf-8",
    )

    probes = (_ProbeConnection(7), _ProbeConnection(11))
    pool = Pool([cast(Any, probes[0]), cast(Any, probes[1])])
    app = App(AppConfig(template_dir=str(tmp_path), skip_contract_checks=True))

    @app.route("/")
    async def index() -> Template:
        conn = await pool.acquire()
        try:
            return Template("page.html", title="stack-ledger", conn_id=conn.identifier)
        finally:
            await pool.release(conn)

    with TestServer(app) as server:
        response = httpx.get(f"{server.url}/", timeout=5.0)
        assert response.status_code == 200
        assert "stack-ledger" in response.text
        assert 'data-conn="7"' in response.text or 'data-conn="11"' in response.text

    assert sys._is_gil_enabled() is False
    assert sum(probe.reset_count for probe in probes) >= 1
