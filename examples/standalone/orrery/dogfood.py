"""Dogfood skills for the Orrery host — N wrapped ``chirp.skill`` apps.

Three astronomy-themed skills with unique tool names so they share one
aggregated ``/mcp``. Each has a golden corpus that passes the publish
oracle (``run_publish_gate`` / smoke harness).
"""

from __future__ import annotations

import hashlib
import os
from typing import Any

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from chirp.skill import Skill
from chirp.skill.smoke import CorpusPrompt

#: How many dogfood skills this host mounts (epic #964 / issue #985).
N_DOGFOOD_SKILLS = 3


def _load_or_generate_key(env_name: str) -> Ed25519PrivateKey:
    raw = os.environ.get(env_name, "").strip()
    if raw:
        return Ed25519PrivateKey.from_private_bytes(bytes.fromhex(raw))
    return Ed25519PrivateKey.generate()


def build_gaze_skill(*, private_key: Any | None = None) -> Skill:
    """Gaze — inspect a named target on the celestial sphere."""
    private = private_key or _load_or_generate_key("ORRERY_GAZE_PRIVATE_KEY")
    public = private.public_key().public_bytes_raw()
    skill = Skill(
        "gaze",
        version="1.0.0",
        private_key=private,
        key_id=os.environ.get("ORRERY_GAZE_KEY_ID", "gaze-1"),
        public_key=public,
    )

    @skill.tool("look_at", description="Inspect a named celestial target")
    def look_at(target: str) -> dict[str, str]:
        digest = hashlib.sha256(target.encode()).hexdigest()[:8]
        return {
            "target": target,
            "bearing": f"{(int(digest, 16) % 360):03d}°",
            "magnitude": f"{(int(digest, 16) % 50) / 10:.1f}",
        }

    return skill


def build_resolve_skill(*, private_key: Any | None = None) -> Skill:
    """Resolve — map a skill name to a stable host path."""
    private = private_key or _load_or_generate_key("ORRERY_RESOLVE_PRIVATE_KEY")
    public = private.public_key().public_bytes_raw()
    skill = Skill(
        "resolve",
        version="1.0.0",
        private_key=private,
        key_id=os.environ.get("ORRERY_RESOLVE_KEY_ID", "resolve-1"),
        public_key=public,
    )

    @skill.tool("resolve_name", description="Resolve a skill name to a host path")
    def resolve_name(name: str) -> dict[str, str]:
        slug = name.strip().lower().replace(" ", "-")
        return {
            "name": name,
            "path": f"/console/{slug}",
            "status": "resolved",
        }

    return skill


def build_star_skill(*, private_key: Any | None = None) -> Skill:
    """Star — seal a short label into a deterministic digest hint."""
    private = private_key or _load_or_generate_key("ORRERY_STAR_PRIVATE_KEY")
    public = private.public_key().public_bytes_raw()
    skill = Skill(
        "star",
        version="1.0.0",
        private_key=private,
        key_id=os.environ.get("ORRERY_STAR_KEY_ID", "star-1"),
        public_key=public,
    )

    @skill.tool("seal_label", description="Seal a label into a digest hint")
    def seal_label(label: str) -> dict[str, str]:
        digest = "sha256:" + hashlib.sha256(label.encode()).hexdigest()[:16]
        return {"label": label, "sealed": "true", "digest": digest}

    return skill


def build_dogfood_skills() -> tuple[Skill, ...]:
    """Return the N dogfood skills in mount order."""
    skills = (
        build_gaze_skill(),
        build_resolve_skill(),
        build_star_skill(),
    )
    assert len(skills) == N_DOGFOOD_SKILLS
    return skills


DOGFOOD_CORPUS: tuple[CorpusPrompt, ...] = (
    CorpusPrompt(
        id="gaze-look-vega",
        prompt="Look at Vega through the gaze skill.",
        tool="look_at",
        arguments={"target": "Vega"},
        required_facts=("Vega",),
    ),
    CorpusPrompt(
        id="resolve-gaze",
        prompt="Resolve the skill named gaze.",
        tool="resolve_name",
        arguments={"name": "gaze"},
        required_facts=("gaze", "resolved", "/console/gaze"),
    ),
    CorpusPrompt(
        id="star-seal-orion",
        prompt="Seal the label Orion.",
        tool="seal_label",
        arguments={"label": "Orion"},
        required_facts=("Orion", "sealed", "sha256:"),
    ),
)
