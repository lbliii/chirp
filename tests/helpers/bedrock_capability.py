"""Shared botocore optional-extra gates for Bedrock capability proof (#915).

Local installs without ``chirp[ai-bedrock]`` soft-skip Bedrock signing tests.
The ``ai-bedrock-capability`` CI lane sets ``CHIRP_REQUIRE_BOTOCORE=1`` so
absence fails closed instead of silently skipping. PR CI remains
credential-free — tests use fixtures / mock HTTP, never live AWS calls.
"""

from __future__ import annotations

import importlib.util
import os

import pytest

_REQUIRE_BOTOCORE_ENV = "CHIRP_REQUIRE_BOTOCORE"


def botocore_package_available() -> bool:
    """True when the optional ``botocore`` package is importable."""
    try:
        return importlib.util.find_spec("botocore") is not None
    except ModuleNotFoundError:
        return False


def ensure_botocore_package() -> None:
    """Skip locally without chirp[ai-bedrock]; fail when the lane requires it."""
    if botocore_package_available():
        return
    if os.environ.get(_REQUIRE_BOTOCORE_ENV) == "1":
        pytest.fail(
            "botocore is required in the ai-bedrock-capability CI lane "
            f"(set via {_REQUIRE_BOTOCORE_ENV}=1); install chirp[ai-bedrock]"
        )
    pytest.skip("requires the optional 'ai-bedrock' extra (botocore)")
