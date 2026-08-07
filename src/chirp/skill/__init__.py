"""Provisional ``chirp.skill`` surface — envelopes, mounting, and manifests.

Import qualified names from this package; nothing here is re-exported from
top-level ``chirp``. See ``docs/public-api.md`` (Provisional Submodule APIs).
"""

from chirp.skill.envelope import Envelope, sign_envelope, verify_envelope
from chirp.skill.manifest import Manifest, assemble_manifest, compute_content_digest
from chirp.skill.mount import Skill, use_skill

__all__ = [
    "Envelope",
    "Manifest",
    "Skill",
    "assemble_manifest",
    "compute_content_digest",
    "sign_envelope",
    "use_skill",
    "verify_envelope",
]
