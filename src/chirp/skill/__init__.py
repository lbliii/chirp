"""Provisional ``chirp.skill`` surface — envelopes, mounting, and manifests.

Import qualified names from this package; nothing here is re-exported from
top-level ``chirp``. See ``docs/public-api.md`` (Provisional Submodule APIs).
"""

from chirp.skill.envelope import Envelope, sign_envelope, verify_envelope
from chirp.skill.manifest import Manifest, assemble_manifest
from chirp.skill.mount import Skill, use_skill

__all__ = [
    "Envelope",
    "Manifest",
    "Skill",
    "assemble_manifest",
    "sign_envelope",
    "use_skill",
    "verify_envelope",
]
