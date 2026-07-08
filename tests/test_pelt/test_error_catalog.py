"""#260: pelt error-code documentation and extraction-export parity."""

import inspect
import re
from pathlib import Path

import pytest

from chirp.data.drivers import _pelt
from chirp.data.drivers._pelt import errors

_ROOT = Path(__file__).resolve().parents[2]
_CATALOG = _ROOT / "docs" / "troubleshooting.md"
_HEADING = re.compile(r"^## (PELT_[A-Z0-9_]+)$", re.MULTILINE)


def _declared_error_types() -> tuple[type[errors.PeltError], ...]:
    return tuple(
        value
        for _name, value in inspect.getmembers(errors, inspect.isclass)
        if value.__module__ == errors.__name__ and issubclass(value, errors.PeltError)
    )


@pytest.mark.issue(260)
def test_every_declared_pelt_error_code_has_a_troubleshooting_heading() -> None:
    headings = set(_HEADING.findall(_CATALOG.read_text(encoding="utf-8")))
    error_types = _declared_error_types()
    codes = {error_type.default_code for error_type in error_types}

    assert all(code.startswith("PELT_") for code in codes)
    assert len(codes) == len(error_types)
    assert codes <= headings


@pytest.mark.issue(260)
def test_dynamic_sqlstate_errors_use_the_finite_catalog_anchor() -> None:
    err = errors.PostgresError(
        "undefined table",
        sqlstate="42P01",
        severity="ERROR",
    )

    assert err.code == "PELT_PG_42P01"
    assert err.doc == "docs/troubleshooting.md#pelt_pg_sqlstate"
    assert '<a id="pelt_pg_sqlstate"></a>' in _CATALOG.read_text(encoding="utf-8")


@pytest.mark.issue(260)
def test_pelt_extraction_exports_are_unique_and_resolvable() -> None:
    expected = {
        "AuthenticationError",
        "Connection",
        "ConnectionConfig",
        "PeltConnectionError",
        "PeltError",
        "PeltTimeoutError",
        "Pool",
        "PoolConfig",
        "PostgresError",
        "ProtocolError",
        "TLSError",
        "connect",
        "create_pool",
    }

    assert len(_pelt.__all__) == len(set(_pelt.__all__))
    assert set(_pelt.__all__) == expected
    for name in _pelt.__all__:
        assert getattr(_pelt, name) is not None


@pytest.mark.issue(260)
def test_error_module_exports_every_declared_error_type() -> None:
    declared_names = {error_type.__name__ for error_type in _declared_error_types()}

    assert set(errors.__all__) == declared_names
    assert all(getattr(errors, name) is not None for name in errors.__all__)
