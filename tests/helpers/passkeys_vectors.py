"""Static WebAuthn ceremony vectors for TestClient integration tests.

Sourced from py_webauthn's ``test_verify_registration_response`` /
``test_verify_authentication_response`` fixtures (localhost / port 5000).
Tests patch ``begin_*`` to stash the matching challenge, then POST the static
credential JSON through the app's finish routes.
"""

from __future__ import annotations

from dataclasses import dataclass

from webauthn.helpers import base64url_to_bytes

from chirp.security.passkeys import PasskeyConfig

TEST_ORIGIN = "http://localhost:5000"
TEST_RP_ID = "localhost"

TEST_PASSKEY_CONFIG = PasskeyConfig(
    rp_id=TEST_RP_ID,
    rp_name="Passkeys Test",
    origin=TEST_ORIGIN,
)

REG_CHALLENGE_B64 = (
    "TwN7n4WTyGKLc4ZY-qGsFqKnHM4nglqsyV0ICJlN2TO9XiRyFtrkaDwUvsql-gkLJXP6fnF1MlrZ53Mm4R7Cvw"
)
REG_CHALLENGE_BYTES = base64url_to_bytes(REG_CHALLENGE_B64)

REG_CREDENTIAL: dict = {
    "id": "9y1xA8Tmg1FEmT-c7_fvWZ_uoTuoih3OvR45_oAK-cwHWhAbXrl2q62iLVTjiyEZ7O7n-CROOY494k7Q3xrs_w",
    "rawId": "9y1xA8Tmg1FEmT-c7_fvWZ_uoTuoih3OvR45_oAK-cwHWhAbXrl2q62iLVTjiyEZ7O7n-CROOY494k7Q3xrs_w",
    "response": {
        "attestationObject": (
            "o2NmbXRkbm9uZWdhdHRTdG10oGhhdXRoRGF0YVjESZYN5YgOjGh0NBcPZHZgW4_krrmihjLHmVzzuoMdl2NF"
            "AAAAFwAAAAAAAAAAAAAAAAAAAAAAQPctcQPE5oNRRJk_nO_371mf7qE7qIodzr0eOf6ACvnMB1oQG165dqutoi1U44sh"
            "Gezu5_gkTjmOPeJO0N8a7P-lAQIDJiABIVggSFbUJF-42Ug3pdM8rDRFu_N5oiVEysPDB6n66r_7dZAiWCDUVnB39Fl"
            "GypL-qAoIO9xWHtJygo2jfDmHl-_eKFRLDA"
        ),
        "clientDataJSON": (
            "eyJ0eXBlIjoid2ViYXV0aG4uY3JlYXRlIiwiY2hhbGxlbmdlIjoiVHdON240V1R5R0tMYzRaWS1xR3NGcUtu"
            "SE00bmdscXN5VjBJQ0psTjJUTzlYaVJ5RnRya2FEd1V2c3FsLWdrTEpYUDZmbkYxTWxyWjUzTW00UjdDdnciLCJvcmln"
            "aW4iOiJodHRwOi8vbG9jYWxob3N0OjUwMDAiLCJjcm9zc09yaWdpbiI6ZmFsc2V9"
        ),
        "transports": ["internal"],
    },
    "type": "public-key",
    "clientExtensionResults": {},
    "authenticatorAttachment": "platform",
}

REG_OPTIONS: dict = {
    "challenge": REG_CHALLENGE_B64,
    "rp": {"name": "Passkeys Test", "id": TEST_RP_ID},
    "user": {
        "id": "dXNlci0x",
        "name": "admin",
        "displayName": "Admin",
    },
    "pubKeyCredParams": [{"type": "public-key", "alg": -7}],
    "timeout": 60000,
    "authenticatorSelection": {
        "residentKey": "preferred",
        "userVerification": "preferred",
    },
    "attestation": "none",
}

AUTH_CHALLENGE_B64 = (
    "xi30GPGAFYRxVDpY1sM10DaLzVQG66nv-_7RUazH0vI2YvG8LYgDEnvN5fZZNVuvEDuMi9te3VLqb42N0fkLGA"
)
AUTH_CHALLENGE_BYTES = base64url_to_bytes(AUTH_CHALLENGE_B64)

AUTH_CREDENTIAL: dict = {
    "id": "EDx9FfAbp4obx6oll2oC4-CZuDidRVV4gZhxC529ytlnqHyqCStDUwfNdm1SNHAe3X5KvueWQdAX3x9R1a2b9Q",
    "rawId": "EDx9FfAbp4obx6oll2oC4-CZuDidRVV4gZhxC529ytlnqHyqCStDUwfNdm1SNHAe3X5KvueWQdAX3x9R1a2b9Q",
    "response": {
        "authenticatorData": "SZYN5YgOjGh0NBcPZHZgW4_krrmihjLHmVzzuoMdl2MBAAAATg",
        "clientDataJSON": (
            "eyJjaGFsbGVuZ2UiOiJ4aTMwR1BHQUZZUnhWRHBZMXNNMTBEYUx6VlFHNjZudi1fN1JVYXpIMHZJMll2RzhMWWdERW52"
            "TjVmWlpOVnV2RUR1TWk5dGUzVkxxYjQyTjBma0xHQSIsImNsaWVudEV4dGVuc2lvbnMiOnt9LCJoYXNoQWxnb3JpdGht"
            "IjoiU0hBLTI1NiIsIm9yaWdpbiI6Imh0dHA6Ly9sb2NhbGhvc3Q6NTAwMCIsInR5cGUiOiJ3ZWJhdXRobi5nZXQifQ"
        ),
        "signature": (
            "MEUCIGisVZOBapCWbnJJvjelIzwpixxIwkjCCb5aCHafQu68AiEA88v-2pJNNApPFwAKFiNuf82-2hBxYW5kGwVweeoxCwo"
        ),
    },
    "type": "public-key",
    "clientExtensionResults": {},
}

AUTH_OPTIONS: dict = {
    "challenge": AUTH_CHALLENGE_B64,
    "timeout": 60000,
    "rpId": TEST_RP_ID,
    "allowCredentials": [
        {
            "type": "public-key",
            "id": AUTH_CREDENTIAL["id"],
        }
    ],
    "userVerification": "preferred",
}


@dataclass(frozen=True, slots=True)
class SeededPasskey:
    """A stored credential matching :data:`AUTH_CREDENTIAL`."""

    credential_id: bytes
    public_key: bytes
    sign_count: int
    user_id: str


def seeded_auth_passkey(user_id: str = "admin") -> SeededPasskey:
    """Return a stored row that verifies with :data:`AUTH_CREDENTIAL`."""
    return SeededPasskey(
        credential_id=base64url_to_bytes(AUTH_CREDENTIAL["id"]),
        public_key=base64url_to_bytes(
            "pQECAyYgASFYIIeDTe-gN8A-zQclHoRnGFWN8ehM1b7yAsa8I8KIvmplIlgg4nFGT5px8o6gpPZZhO01wdy9crDSA_Ngtkx0vGpvPHI"
        ),
        sign_count=77,
        user_id=user_id,
    )


def patch_fixed_ceremony(monkeypatch) -> None:
    """Stash the static challenges and return the static options dicts."""

    def _fake_begin_registration(**kwargs):
        from chirp.security.passkeys import _stash_challenge

        _stash_challenge(REG_CHALLENGE_BYTES, ttl=300)
        return REG_OPTIONS

    def _fake_begin_authentication(**kwargs):
        from chirp.security.passkeys import _stash_challenge

        _stash_challenge(AUTH_CHALLENGE_BYTES, ttl=300)
        return AUTH_OPTIONS

    monkeypatch.setattr(
        "chirp.security.passkeys.begin_registration",
        _fake_begin_registration,
    )
    monkeypatch.setattr(
        "chirp.security.passkeys.begin_authentication",
        _fake_begin_authentication,
    )
