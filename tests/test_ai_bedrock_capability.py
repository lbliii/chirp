"""Bedrock / chirp[ai-bedrock] capability proof (#915).

Default installs keep ``chirp[ai-bedrock]`` optional. The specialized
``ai-bedrock-capability`` CI lane installs the extra and sets
``CHIRP_REQUIRE_BOTOCORE=1`` so package absence fails instead of skipping.

PR CI is credential-safe: botocore signs a mock HTTP request with fixture
credentials — no live AWS Bedrock calls, no billable network.
"""

from __future__ import annotations

import os

import pytest

pytest.importorskip("httpx")

from chirp.ai.llm import LLM
from chirp.testing.eval import install_mock_transport
from tests.helpers.bedrock_capability import (
    _REQUIRE_BOTOCORE_ENV,
    botocore_package_available,
    ensure_botocore_package,
)


@pytest.mark.issue(915)
def test_capability_lane_requires_botocore_package() -> None:
    """ai-bedrock-capability CI must install chirp[ai-bedrock]; default stays optional."""
    if os.environ.get(_REQUIRE_BOTOCORE_ENV) != "1":
        return
    assert botocore_package_available(), (
        "chirp[ai-bedrock] / botocore missing in ai-bedrock-capability lane"
    )


@pytest.mark.issue(915)
@pytest.mark.asyncio
async def test_bedrock_generate_signs_with_botocore(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Botocore SigV4 signing path works against a deterministic mock transport."""
    ensure_botocore_package()
    import botocore.session
    import httpx

    class _Creds:
        access_key = "AKIATEST"
        secret_key = "secret"
        token = None

        def get_frozen_credentials(self):
            return self

    session = botocore.session.get_session()
    monkeypatch.setattr(session, "get_credentials", lambda: _Creds())
    monkeypatch.setattr("botocore.session.get_session", lambda: session)

    def handler(request: httpx.Request) -> httpx.Response:
        assert "/converse" in request.url.path
        assert request.headers.get("authorization", "").startswith("AWS4-HMAC-SHA256")
        return httpx.Response(
            200,
            json={"output": {"message": {"content": [{"text": "Bedrock ok"}]}}},
        )

    install_mock_transport(monkeypatch, handler)
    llm = LLM("bedrock:anthropic.claude-3-haiku-20240307-v1:0")
    text = await llm.generate("Hello")
    assert text == "Bedrock ok"
