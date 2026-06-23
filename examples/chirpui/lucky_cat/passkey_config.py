"""Passkey relying-party config — env-aware for Railway deploy."""

from __future__ import annotations

import os

from chirp.security.passkeys import PasskeyConfig

# WebAuthn requires rp_id to be a registrable suffix of origin. Override on Railway:
#   CHIRP_PASSKEY_RP_ID=your-app.up.railway.app
#   CHIRP_PASSKEY_ORIGIN=https://your-app.up.railway.app
_ORIGIN = os.environ.get("CHIRP_PASSKEY_ORIGIN", "http://localhost:8000")
_RP_ID = os.environ.get("CHIRP_PASSKEY_RP_ID", "localhost")

PASSKEY_CONFIG = PasskeyConfig(
    rp_id=_RP_ID,
    rp_name="Lucky Cat",
    origin=_ORIGIN,
)
