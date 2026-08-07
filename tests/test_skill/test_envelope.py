"""Proof for #969 — Envelope sign/verify + negotiate wire JSON."""

from __future__ import annotations

import json
from dataclasses import replace

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from chirp.server.negotiation import negotiate
from chirp.skill import Envelope, sign_envelope, verify_envelope


def _keypair() -> tuple[Ed25519PrivateKey, bytes]:
    private = Ed25519PrivateKey.generate()
    return private, private.public_key().public_bytes_raw()


@pytest.mark.issue(969)
class TestEnvelopeIssue969:
    def test_sign_verify_round_trip(self) -> None:
        private, public = _keypair()
        env = sign_envelope(
            payload={"answer": 42},
            skill="demo",
            version="1.0.0",
            tool="add",
            input_digest="sha256:abc",
            private_key=private,
            key_id="demo-key-1",
            nonce="fixed-nonce",
        )
        assert env.alg == "Ed25519"
        assert env.nonce == "fixed-nonce"
        assert verify_envelope(env, public) is True

    def test_mutated_payload_fails_verification(self) -> None:
        private, public = _keypair()
        env = sign_envelope(
            payload={"answer": 42},
            skill="demo",
            version="1.0.0",
            tool="add",
            input_digest="sha256:abc",
            private_key=private,
            key_id="demo-key-1",
        )
        tampered = replace(env, payload={"answer": 99})
        assert verify_envelope(tampered, public) is False
        assert verify_envelope(env, public) is True

    def test_negotiate_emits_signed_json_body(self) -> None:
        private, _public = _keypair()
        env = sign_envelope(
            payload={"ok": True},
            skill="demo",
            version="0.1.0",
            tool="ping",
            input_digest="sha256:deadbeef",
            private_key=private,
            key_id="k1",
            nonce="n1",
        )
        response = negotiate(env)
        assert "application/json" in response.content_type
        body = json.loads(response.text)
        assert body == {
            "payload": {"ok": True},
            "skill": "demo",
            "version": "0.1.0",
            "tool": "ping",
            "nonce": "n1",
            "input_digest": "sha256:deadbeef",
            "signature": env.signature,
            "key_id": "k1",
            "alg": "Ed25519",
        }
        # Reconstructed Envelope from wire still verifies.
        reconstructed = Envelope(**body)
        assert verify_envelope(reconstructed, private.public_key()) is True
