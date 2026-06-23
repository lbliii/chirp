"""Conftest — keep passkeys_minimal modules importable during collection."""

import sys
from pathlib import Path

import pytest

_HERE = Path(__file__).parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))


@pytest.fixture(autouse=True)
def _passkeys_minimal_on_path():
    yield
