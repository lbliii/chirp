"""Dogfood skills for the Orrery host — N wrapped ``chirp.skill`` apps.

Three astronomy-themed skills plus seven trust-workflow skills with unique
tool names so they share one aggregated ``/mcp``. Each has a deterministic,
offline-safe golden corpus that passes the publish oracle
(``run_publish_gate`` / smoke harness).
"""

from __future__ import annotations

import hashlib
import os
from typing import Any

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from chirp.skill import Skill
from chirp.skill.smoke import CorpusPrompt

#: How many dogfood skills this host mounts (epic #964 / issue #985).
N_DOGFOOD_SKILLS = 10


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


def build_mcp_verify_skill(*, private_key: Any | None = None) -> Skill:
    """MCP Verify — issue a deterministic compatibility receipt."""
    private = private_key or _load_or_generate_key("ORRERY_MCP_VERIFY_PRIVATE_KEY")
    public = private.public_key().public_bytes_raw()
    skill = Skill(
        "mcp-verify",
        version="1.0.0",
        private_key=private,
        key_id=os.environ.get("ORRERY_MCP_VERIFY_KEY_ID", "mcp-verify-1"),
        public_key=public,
    )

    @skill.tool("verify_mcp", description="Issue an offline MCP compatibility receipt")
    def verify_mcp(endpoint: str) -> dict[str, str]:
        return {
            "endpoint": endpoint,
            "transport": "streamable-http",
            "protocol": "2026-07-28",
            "status": "compatible-demo",
        }

    return skill


def build_release_readiness_skill(*, private_key: Any | None = None) -> Skill:
    """Release Readiness — gate a revision on declared CI status."""
    private = private_key or _load_or_generate_key("ORRERY_RELEASE_READINESS_PRIVATE_KEY")
    public = private.public_key().public_bytes_raw()
    skill = Skill(
        "release-readiness",
        version="1.0.0",
        private_key=private,
        key_id=os.environ.get("ORRERY_RELEASE_READINESS_KEY_ID", "release-readiness-1"),
        public_key=public,
    )

    @skill.tool("release_readiness", description="Gate a revision on its declared CI state")
    def release_readiness(revision: str, ci_passed: bool) -> dict[str, str]:
        return {
            "revision": revision,
            "ci": "passed" if ci_passed else "failed",
            "decision": "ready" if ci_passed else "blocked",
            "policy": "demo-release-policy-v1",
        }

    return skill


def build_production_receipt_skill(*, private_key: Any | None = None) -> Skill:
    """Production Receipt — confirm a named deployment deterministically."""
    private = private_key or _load_or_generate_key("ORRERY_PRODUCTION_RECEIPT_PRIVATE_KEY")
    public = private.public_key().public_bytes_raw()
    skill = Skill(
        "production-receipt",
        version="1.0.0",
        private_key=private,
        key_id=os.environ.get("ORRERY_PRODUCTION_RECEIPT_KEY_ID", "production-receipt-1"),
        public_key=public,
    )

    @skill.tool("production_receipt", description="Issue a deterministic deployment receipt")
    def production_receipt(deployment: str) -> dict[str, str]:
        digest = hashlib.sha256(deployment.encode()).hexdigest()[:12]
        return {
            "deployment": deployment,
            "state": "healthy-demo",
            "receipt": f"sha256:{digest}",
            "observation": "offline-fixture",
        }

    return skill


def build_artifact_qa_skill(*, private_key: Any | None = None) -> Skill:
    """Artifact QA — report a deterministic artifact-quality receipt."""
    private = private_key or _load_or_generate_key("ORRERY_ARTIFACT_QA_PRIVATE_KEY")
    public = private.public_key().public_bytes_raw()
    skill = Skill(
        "artifact-qa",
        version="1.0.0",
        private_key=private,
        key_id=os.environ.get("ORRERY_ARTIFACT_QA_KEY_ID", "artifact-qa-1"),
        public_key=public,
    )

    @skill.tool("artifact_qa", description="Check declared artifact requirements offline")
    def artifact_qa(artifact: str, required_sections: int) -> dict[str, str]:
        return {
            "artifact": artifact,
            "required_sections": str(required_sections),
            "status": "passed-demo",
            "checklist": "render,content,export",
        }

    return skill


def build_research_evidence_skill(*, private_key: Any | None = None) -> Skill:
    """Research Evidence — preserve an offline illustrative evidence bundle."""
    private = private_key or _load_or_generate_key("ORRERY_RESEARCH_EVIDENCE_PRIVATE_KEY")
    public = private.public_key().public_bytes_raw()
    skill = Skill(
        "research-evidence",
        version="1.0.0",
        private_key=private,
        key_id=os.environ.get("ORRERY_RESEARCH_EVIDENCE_KEY_ID", "research-evidence-1"),
        public_key=public,
    )

    @skill.tool("research_evidence", description="Create an offline illustrative evidence receipt")
    def research_evidence(question: str) -> dict[str, str]:
        digest = hashlib.sha256(question.encode()).hexdigest()[:12]
        return {
            "question": question,
            "evidence_set": f"offline-demo:{digest}",
            "sources": "0-live; fixture-only",
            "confidence": "illustrative",
        }

    return skill


def build_handoff_receipt_skill(*, private_key: Any | None = None) -> Skill:
    """Handoff Receipt — record a scoped owner and change summary."""
    private = private_key or _load_or_generate_key("ORRERY_HANDOFF_RECEIPT_PRIVATE_KEY")
    public = private.public_key().public_bytes_raw()
    skill = Skill(
        "handoff-receipt",
        version="1.0.0",
        private_key=private,
        key_id=os.environ.get("ORRERY_HANDOFF_RECEIPT_KEY_ID", "handoff-receipt-1"),
        public_key=public,
    )

    @skill.tool("handoff_receipt", description="Record a deterministic operational handoff")
    def handoff_receipt(change: str, owner: str) -> dict[str, str]:
        return {
            "change": change,
            "owner": owner,
            "status": "handed-off-demo",
            "next_step": "verify-before-action",
        }

    return skill


def build_reliability_status_skill(*, private_key: Any | None = None) -> Skill:
    """Reliability Status — publish a deterministic illustrative score."""
    private = private_key or _load_or_generate_key("ORRERY_RELIABILITY_STATUS_PRIVATE_KEY")
    public = private.public_key().public_bytes_raw()
    skill = Skill(
        "reliability-status",
        version="1.0.0",
        private_key=private,
        key_id=os.environ.get("ORRERY_RELIABILITY_STATUS_KEY_ID", "reliability-status-1"),
        public_key=public,
    )

    @skill.tool(
        "reliability_status", description="Return an illustrative offline reliability status"
    )
    def reliability_status(skill_name: str) -> dict[str, str]:
        return {
            "skill": skill_name,
            "smoke": "passed-demo",
            "reliability": "100%-fixture",
            "window": "offline-corpus-v1",
        }

    return skill


def build_dogfood_skills() -> tuple[Skill, ...]:
    """Return the N dogfood skills in mount order."""
    skills = (
        build_gaze_skill(),
        build_resolve_skill(),
        build_star_skill(),
        build_mcp_verify_skill(),
        build_release_readiness_skill(),
        build_production_receipt_skill(),
        build_artifact_qa_skill(),
        build_research_evidence_skill(),
        build_handoff_receipt_skill(),
        build_reliability_status_skill(),
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
    CorpusPrompt(
        id="mcp-verify-orrery",
        prompt="Verify the Orrery MCP endpoint without a network request.",
        tool="verify_mcp",
        arguments={"endpoint": "https://orrery.example/mcp"},
        required_facts=("orrery.example/mcp", "streamable-http", "compatible-demo"),
    ),
    CorpusPrompt(
        id="release-readiness-green",
        prompt="Check whether revision demo-123 is ready after passing CI.",
        tool="release_readiness",
        arguments={"revision": "demo-123", "ci_passed": True},
        required_facts=("demo-123", "passed", "ready", "demo-release-policy-v1"),
    ),
    CorpusPrompt(
        id="production-receipt-demo",
        prompt="Issue a production receipt for deploy-demo-1.",
        tool="production_receipt",
        arguments={"deployment": "deploy-demo-1"},
        required_facts=("deploy-demo-1", "healthy-demo", "sha256:", "offline-fixture"),
    ),
    CorpusPrompt(
        id="artifact-qa-report",
        prompt="Check the release report with three required sections.",
        tool="artifact_qa",
        arguments={"artifact": "release-report.pdf", "required_sections": 3},
        required_facts=("release-report.pdf", "3", "passed-demo", "render,content,export"),
    ),
    CorpusPrompt(
        id="research-evidence-question",
        prompt="Create evidence for the given platform question.",
        tool="research_evidence",
        arguments={"question": "What proves a trusted skill?"},
        required_facts=(
            "What proves a trusted skill?",
            "offline-demo:",
            "fixture-only",
            "illustrative",
        ),
    ),
    CorpusPrompt(
        id="handoff-receipt-owner",
        prompt="Hand off the release checklist to the release owner.",
        tool="handoff_receipt",
        arguments={"change": "release checklist", "owner": "release-owner"},
        required_facts=(
            "release checklist",
            "release-owner",
            "handed-off-demo",
            "verify-before-action",
        ),
    ),
    CorpusPrompt(
        id="reliability-status-gaze",
        prompt="Show the fixture reliability status for gaze.",
        tool="reliability_status",
        arguments={"skill_name": "gaze"},
        required_facts=("gaze", "passed-demo", "100%-fixture", "offline-corpus-v1"),
    ),
)
