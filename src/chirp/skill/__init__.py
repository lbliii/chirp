"""Provisional ``chirp.skill`` surface — envelopes, mounting, and manifests.

Import qualified names from this package; nothing here is re-exported from
top-level ``chirp``. See ``docs/public-api.md`` (Provisional Submodule APIs).
"""

from chirp.skill.console import (
    DEFAULT_CONSOLE_PATH,
    ReliabilityScore,
    ReliabilityStore,
    mount_console,
)
from chirp.skill.envelope import Envelope, sign_envelope, verify_envelope
from chirp.skill.manifest import Manifest, assemble_manifest, compute_content_digest
from chirp.skill.mount import Skill, use_skill
from chirp.skill.registry import DEFAULT_DISCOVERY_PATH, SkillRegistry, mount_skills
from chirp.tools.live_log import DEFAULT_INVOCATION_LOG_PATH

__all__ = [
    "DEFAULT_CONSOLE_PATH",
    "DEFAULT_DISCOVERY_PATH",
    "DEFAULT_INVOCATION_LOG_PATH",
    "Envelope",
    "Manifest",
    "ReliabilityScore",
    "ReliabilityStore",
    "Skill",
    "SkillRegistry",
    "assemble_manifest",
    "compute_content_digest",
    "mount_console",
    "mount_skills",
    "sign_envelope",
    "use_skill",
    "verify_envelope",
]
