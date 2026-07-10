"""Source-backed decision checks for private signal-backplane RFC #678."""

from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
_RFC = _ROOT / "docs" / "rfcs" / "023-private-signal-backplane.md"


@pytest.mark.issue(678)
def test_signal_backplane_rfc_is_accepted_but_non_shipping() -> None:
    text = _RFC.read_text(encoding="utf-8")
    normalized = " ".join(text.split())

    assert "**Status:** Accepted design; not implemented" in text
    assert "**Shipping impact:** None" in text
    assert "no `AppConfig.signal_bus`" in normalized
    assert "no `app.set_signal_bus()`" in normalized
    assert "no exported or `runtime_checkable` protocol" in normalized


@pytest.mark.issue(678)
def test_signal_backplane_rfc_freezes_private_selection_and_lifecycle() -> None:
    text = _RFC.read_text(encoding="utf-8")
    normalized = " ".join(text.split())

    for phrase in (
        "registered signals plus an empty `config.redis_url` selects memory",
        "registered signals plus a non-empty `config.redis_url` selects Redis",
        "never falls back to memory",
        "bound to the registry exactly once",
        "The application lifespan owns the selected adapter coordinator",
        "Close is idempotent",
    ):
        assert phrase in normalized


@pytest.mark.issue(678)
def test_signal_backplane_rfc_makes_audience_authority_server_side() -> None:
    text = _RFC.read_text(encoding="utf-8")
    normalized = " ".join(text.split())

    for phrase in (
        "reject any legacy or forged `aud` parameter",
        "return 400 for an unknown name",
        "return 403 when a session-scoped signal is requested",
        "versioned HMAC",
        "exact `SUBSCRIBE`, never `PSUBSCRIBE signal:*`",
        "must not record the raw audience key",
    ):
        assert phrase in normalized


@pytest.mark.issue(678)
def test_signal_backplane_rfc_freezes_delivery_and_diagnostic_limits() -> None:
    text = _RFC.read_text(encoding="utf-8")
    normalized = " ".join(text.split())

    for phrase in (
        "`source=` async generators remain local to the SSE connection",
        "coalescing-latest",
        "no transparent broker reconnect",
        "`coalesce=False` append-style mode is not supported",
        "category `signal_bus_single_worker`",
        "Signals use a process-local bus with workers={workers}",
        "Set AppConfig(workers=1), or configure AppConfig(redis_url=...)",
        "CLI `--workers` override",
    ):
        assert phrase in normalized
