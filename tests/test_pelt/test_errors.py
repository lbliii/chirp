"""E1.2 (#265) — PeltError tree: codes, hints, SQLSTATE, and pickle round-trip."""

import pickle

import pytest

from chirp.data.drivers._pelt.errors import (
    PeltConnectionError,
    PeltError,
    PostgresError,
    ProtocolError,
)
from chirp.data.errors import DataError


@pytest.mark.issue(265)
def test_pelt_error_nests_under_dataerror():
    # While in-tree, existing `except DataError` handlers must still catch pelt errors.
    assert issubclass(PeltError, DataError)


@pytest.mark.issue(265)
def test_default_code_and_doc_anchor():
    err = PeltConnectionError("could not connect")
    assert err.code == "PELT_CONN_FAILED"
    assert err.doc == "docs/troubleshooting.md#pelt_conn_failed"
    assert err.hint is None


@pytest.mark.issue(265)
def test_explicit_code_hint_doc_override():
    err = PeltError("boom", code="PELT_X", hint="do the thing", doc="d.md#x")
    assert (err.code, err.hint, err.doc) == ("PELT_X", "do the thing", "d.md#x")


@pytest.mark.issue(265)
def test_postgres_error_carries_sqlstate():
    err = PostgresError(
        "relation does not exist",
        sqlstate="42P01",
        severity="ERROR",
        detail="table foo missing",
        hint="create it first",
    )
    assert err.code == "PELT_PG_42P01"
    assert err.sqlstate == "42P01"
    assert err.severity == "ERROR"
    assert err.detail == "table foo missing"
    assert err.hint == "create it first"


@pytest.mark.issue(265)
@pytest.mark.parametrize(
    "err",
    [
        PeltError("plain"),
        ProtocolError("desync"),
        PostgresError("e", sqlstate="42P01", severity="ERROR", detail="d"),
    ],
)
def test_pickle_round_trip_preserves_state(err):
    restored = pickle.loads(pickle.dumps(err))  # noqa: S301 — round-tripping our own errors
    assert type(restored) is type(err)
    assert restored.args == err.args
    assert restored.code == err.code
    assert restored.doc == err.doc
    if isinstance(err, PostgresError):
        assert restored.sqlstate == err.sqlstate
        assert restored.severity == err.severity
        assert restored.detail == err.detail
