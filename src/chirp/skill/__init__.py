"""Provisional ``chirp.skill`` surface — signed envelopes and (later) mounting.

Import qualified names from this package; nothing here is re-exported from
top-level ``chirp``. See ``docs/public-api.md`` (Provisional Submodule APIs).
"""

from chirp.skill.envelope import Envelope, sign_envelope, verify_envelope

__all__ = [
    "Envelope",
    "sign_envelope",
    "verify_envelope",
]
