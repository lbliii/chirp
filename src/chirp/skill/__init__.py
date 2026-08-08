"""Provisional ``chirp.skill`` surface — envelopes, mounting, and manifests.

Import qualified names from this package; nothing here is re-exported from
top-level ``chirp``. See ``docs/public-api.md`` (Provisional Submodule APIs).
"""

from chirp.skill.envelope import Envelope, sign_envelope, verify_envelope
from chirp.skill.keystore import (
    KEY_STATUS_TOOL,
    EnvKeystore,
    KeyStatus,
    SecretLeakError,
    assert_no_secret_leak,
    register_key_status_tool,
)
from chirp.skill.manifest import Manifest, assemble_manifest, compute_content_digest
from chirp.skill.mount import Skill, use_skill
from chirp.skill.registry import DEFAULT_DISCOVERY_PATH, SkillRegistry, mount_skills

__all__ = [
    "DEFAULT_DISCOVERY_PATH",
    "KEY_STATUS_TOOL",
    "EnvKeystore",
    "Envelope",
    "KeyStatus",
    "Manifest",
    "SecretLeakError",
    "Skill",
    "SkillRegistry",
    "assemble_manifest",
    "assert_no_secret_leak",
    "compute_content_digest",
    "mount_skills",
    "register_key_status_tool",
    "sign_envelope",
    "use_skill",
    "verify_envelope",
]
