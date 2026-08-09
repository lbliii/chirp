"""Shared python-dotenv optional-extra gates for capability proof (#915).

Local installs without ``chirp[config]`` soft-skip dotenv behavioral tests.
The ``config-capability`` CI lane sets ``CHIRP_REQUIRE_DOTENV=1`` so absence
fails closed instead of silently skipping.
"""

from __future__ import annotations

import importlib.util
import os

import pytest

_REQUIRE_DOTENV_ENV = "CHIRP_REQUIRE_DOTENV"


def dotenv_package_available() -> bool:
    """True when the optional ``python-dotenv`` package is importable."""
    try:
        return importlib.util.find_spec("dotenv") is not None
    except ModuleNotFoundError:
        return False


def ensure_dotenv_package() -> None:
    """Skip locally without chirp[config]; fail when the capability lane requires it."""
    if dotenv_package_available():
        return
    if os.environ.get(_REQUIRE_DOTENV_ENV) == "1":
        pytest.fail(
            "python-dotenv is required in the config-capability CI lane "
            f"(set via {_REQUIRE_DOTENV_ENV}=1); install chirp[config]"
        )
    pytest.skip("requires the optional 'config' extra (python-dotenv)")
