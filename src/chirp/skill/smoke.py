"""Skill smoke harness — golden NL corpus + faithful-answer scorer.

Agentic-COBOL methodology (InvestorClaw / Orrery publish oracle): a skill
passes smoke only when each corpus prompt yields an answer that is faithful
to the tool's engine JSON — not a refusal, capability catalog, or
section-skip fallback.

This module is the L3.2 harness; publish-gate wiring lives in
``chirp.skill.publish`` / ``chirp skill publish``.
"""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from chirp.skill.envelope import Envelope

# Failure classes surfaced on SmokeVerdict.failure_class
FAILURE_REFUSAL = "refusal"
FAILURE_CATALOG = "catalog"
FAILURE_SECTION_SKIP = "section_skip"
FAILURE_UNFAITHFUL = "unfaithful"
FAILURE_EMPTY = "empty"

# Agentic-COBOL rejection markers (case-insensitive substring match).
_REFUSAL_MARKERS: tuple[str, ...] = (
    "i don't have data on that",
    "i do not have data on that",
    "i can't help with that",
    "i cannot help with that",
    "i cannot answer that without making up numbers",
    "i can't answer that without making up numbers",
    "as an ai",
    "i'm not able to",
    "i am not able to",
)

_SECTION_SKIP_MARKERS: tuple[str, ...] = (
    "section did not run",
    "section skipped",
    "section was skipped",
    "skipped this section",
)

# Capability-catalog blurbs: narrator lists tools instead of answering.
_CATALOG_MARKERS: tuple[str, ...] = (
    "what i can help with",
    "here are the tools i can use",
    "available commands",
    "i can help with the following",
    "completed your portfolio analysis with",
    "here is what i can do",
)

_MIN_BODY_CHARS = 24


@dataclass(frozen=True, slots=True)
class CorpusPrompt:
    """One golden natural-language prompt tied to a skill tool invocation."""

    id: str
    prompt: str
    tool: str
    arguments: Mapping[str, Any] = field(default_factory=dict)
    #: Substrings that a faithful answer must surface from the engine payload.
    required_facts: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.id, str) or not self.id.strip():
            msg = "CorpusPrompt.id must be a non-empty string"
            raise ValueError(msg)
        if not isinstance(self.prompt, str) or not self.prompt.strip():
            msg = "CorpusPrompt.prompt must be a non-empty string"
            raise ValueError(msg)
        if not isinstance(self.tool, str) or not self.tool.strip():
            msg = "CorpusPrompt.tool must be a non-empty string"
            raise ValueError(msg)
        # Freeze a plain dict copy so callers cannot mutate after construction.
        object.__setattr__(self, "arguments", dict(self.arguments))


@dataclass(frozen=True, slots=True)
class SmokeVerdict:
    """Pass/fail result for one answer scored against engine JSON."""

    passed: bool
    reason: str
    failure_class: str | None = None


@dataclass(frozen=True, slots=True)
class SmokeResult:
    """Per-prompt smoke outcome."""

    prompt_id: str
    tool: str
    verdict: SmokeVerdict
    engine_payload: Any
    answer: str


@dataclass(frozen=True, slots=True)
class SmokeReport:
    """Aggregate report for a corpus run."""

    results: tuple[SmokeResult, ...]

    @property
    def passed(self) -> bool:
        return all(r.verdict.passed for r in self.results)

    @property
    def failures(self) -> tuple[SmokeResult, ...]:
        return tuple(r for r in self.results if not r.verdict.passed)


AnswerFn = Callable[[CorpusPrompt, Any], str]
AsyncToolCaller = Callable[[str, Mapping[str, Any]], Awaitable[Any]]


def _flatten_facts(engine_json: Any) -> list[str]:
    """Extract scorable string facts from engine JSON (payload or wire dict)."""
    if isinstance(engine_json, Envelope):
        return _flatten_facts(engine_json.payload)

    facts: list[str] = []

    def _walk(value: Any) -> None:
        if value is None:
            return
        if isinstance(value, bool):
            facts.append("true" if value else "false")
            return
        if isinstance(value, (int, float)):
            facts.append(str(value))
            return
        if isinstance(value, str):
            text = value.strip()
            if text:
                facts.append(text)
            return
        if isinstance(value, Mapping):
            for k, v in value.items():
                if isinstance(k, str) and k.strip():
                    facts.append(k.strip())
                _walk(v)
            return
        if isinstance(value, (list, tuple)):
            for item in value:
                _walk(item)
            return
        facts.append(str(value))

    _walk(engine_json)
    return facts


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def _find_marker(answer_norm: str, markers: Sequence[str]) -> str | None:
    for marker in markers:
        if marker in answer_norm:
            return marker
    return None


def score_answer(
    answer: str,
    engine_json: Any,
    *,
    required_facts: Sequence[str] = (),
) -> SmokeVerdict:
    """Score a user-facing answer against engine JSON (Agentic-COBOL verdict).

    Failures (checked in order):
    - empty / stub body
    - refusal markers
    - section-skip markers
    - capability-catalog blurbs
    - missing required facts (or no overlap with engine JSON facts)
    """
    if not isinstance(answer, str):
        return SmokeVerdict(
            passed=False,
            reason="answer must be a string",
            failure_class=FAILURE_EMPTY,
        )

    body = answer.strip()
    if len(body) < _MIN_BODY_CHARS:
        return SmokeVerdict(
            passed=False,
            reason=f"answer too short ({len(body)} < {_MIN_BODY_CHARS} chars)",
            failure_class=FAILURE_EMPTY,
        )

    answer_norm = _normalize(body)

    marker = _find_marker(answer_norm, _REFUSAL_MARKERS)
    if marker is not None:
        return SmokeVerdict(
            passed=False,
            reason=f"refusal marker: {marker!r}",
            failure_class=FAILURE_REFUSAL,
        )

    marker = _find_marker(answer_norm, _SECTION_SKIP_MARKERS)
    if marker is not None:
        return SmokeVerdict(
            passed=False,
            reason=f"section-skip marker: {marker!r}",
            failure_class=FAILURE_SECTION_SKIP,
        )

    marker = _find_marker(answer_norm, _CATALOG_MARKERS)
    if marker is not None:
        return SmokeVerdict(
            passed=False,
            reason=f"capability catalog marker: {marker!r}",
            failure_class=FAILURE_CATALOG,
        )

    required = tuple(f for f in required_facts if str(f).strip())
    if required:
        missing = [fact for fact in required if _normalize(str(fact)) not in answer_norm]
        if missing:
            return SmokeVerdict(
                passed=False,
                reason=f"missing required facts: {missing!r}",
                failure_class=FAILURE_UNFAITHFUL,
            )
    else:
        # Require at least one distinctive engine fact to appear in the answer.
        facts = {str(f).strip() for f in _flatten_facts(engine_json) if len(str(f).strip()) >= 2}
        distinctive: list[str] = sorted(facts, key=lambda s: len(s), reverse=True)
        if distinctive and not any(_normalize(fact) in answer_norm for fact in distinctive):
            return SmokeVerdict(
                passed=False,
                reason="answer shares no facts with engine JSON",
                failure_class=FAILURE_UNFAITHFUL,
            )

    return SmokeVerdict(passed=True, reason="faithful", failure_class=None)


def render_faithful_answer(prompt: CorpusPrompt, engine_json: Any) -> str:
    """Default answer_fn: narrate engine JSON facts (used by the fixture harness)."""
    payload = engine_json.payload if isinstance(engine_json, Envelope) else engine_json
    if isinstance(payload, Mapping):
        parts = [f"{k}: {v}" for k, v in payload.items()]
        body = "; ".join(parts)
    else:
        body = json.dumps(payload, default=str, ensure_ascii=False)
    return f"For {prompt.prompt.strip()} — {body}"


def _unwrap_payload(result: Any) -> Any:
    if isinstance(result, Envelope):
        return result.payload
    return result


async def _call_tool(app: Any, tool: str, arguments: Mapping[str, Any]) -> Any:
    return await app.tools.call_tool(tool, dict(arguments))


def run_smoke(
    app: Any,
    corpus: Sequence[CorpusPrompt],
    *,
    answer_fn: AnswerFn | None = None,
    call_tool: AsyncToolCaller | None = None,
) -> SmokeReport:
    """Run the golden corpus against a frozen app's MCP tools and score answers.

    ``answer_fn(prompt, engine_payload)`` supplies the user-facing narrative
    scored against the tool result. Defaults to :func:`render_faithful_answer`
    so a correctly mounted fixture skill passes end-to-end.
    """
    if not corpus:
        msg = "corpus must contain at least one CorpusPrompt"
        raise ValueError(msg)

    narrator = answer_fn or render_faithful_answer
    caller = call_tool

    async def _run_all() -> list[SmokeResult]:
        out: list[SmokeResult] = []
        for entry in corpus:
            if caller is not None:
                raw = await caller(entry.tool, entry.arguments)
            else:
                raw = await _call_tool(app, entry.tool, entry.arguments)
            payload = _unwrap_payload(raw)
            answer = narrator(entry, payload if not isinstance(raw, Envelope) else raw)
            # Prefer Envelope for fact extraction when present.
            engine = raw if isinstance(raw, Envelope) else payload
            verdict = score_answer(answer, engine, required_facts=entry.required_facts)
            out.append(
                SmokeResult(
                    prompt_id=entry.id,
                    tool=entry.tool,
                    verdict=verdict,
                    engine_payload=payload,
                    answer=answer,
                )
            )
        return out

    results = tuple(asyncio.run(_run_all()))
    return SmokeReport(results=results)


# ---------------------------------------------------------------------------
# Fixture skill (proof / publish-oracle demo)
# ---------------------------------------------------------------------------

FIXTURE_SKILL_NAME = "fixture-echo"
FIXTURE_SKILL_VERSION = "1.0.0"

FIXTURE_CORPUS: tuple[CorpusPrompt, ...] = (
    CorpusPrompt(
        id="fx-echo-1",
        prompt="Echo back the greeting for Alice.",
        tool="echo",
        arguments={"message": "Hello, Alice"},
        required_facts=("Hello, Alice",),
    ),
    CorpusPrompt(
        id="fx-weather-1",
        prompt="What's the weather in Lisbon?",
        tool="weather",
        arguments={"city": "Lisbon"},
        required_facts=("Lisbon", "sunny"),
    ),
)


def make_fixture_skill(
    *,
    private_key: Any | None = None,
    key_id: str = "fixture-1",
) -> Any:
    """Build a minimal signed skill with ``echo`` + ``weather`` tools.

    Used by tests and as the canonical smoke fixture for the publish oracle.
    Generates an Ed25519 keypair when ``private_key`` is omitted (requires
    ``chirp[skill]`` / cryptography).
    """
    from chirp.skill.mount import Skill

    if private_key is None:
        try:
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        except ImportError as exc:  # pragma: no cover - packaging posture
            msg = (
                "make_fixture_skill requires the 'cryptography' package. "
                "Install it with: pip install 'chirp[skill]'"
            )
            raise ImportError(msg) from exc
        private_key = Ed25519PrivateKey.generate()

    public = private_key.public_key().public_bytes_raw()
    skill = Skill(
        FIXTURE_SKILL_NAME,
        version=FIXTURE_SKILL_VERSION,
        private_key=private_key,
        key_id=key_id,
        public_key=public,
    )

    @skill.tool("echo", description="Echo a message back to the caller")
    def echo(message: str) -> dict[str, str]:
        return {"message": message, "echoed": "true"}

    @skill.tool("weather", description="Return a deterministic weather summary for a city")
    def weather(city: str) -> dict[str, str]:
        return {"city": city, "summary": "sunny", "temp_c": "22"}

    return skill


__all__ = [
    "FAILURE_CATALOG",
    "FAILURE_EMPTY",
    "FAILURE_REFUSAL",
    "FAILURE_SECTION_SKIP",
    "FAILURE_UNFAITHFUL",
    "FIXTURE_CORPUS",
    "FIXTURE_SKILL_NAME",
    "FIXTURE_SKILL_VERSION",
    "CorpusPrompt",
    "SmokeReport",
    "SmokeResult",
    "SmokeVerdict",
    "make_fixture_skill",
    "render_faithful_answer",
    "run_smoke",
    "score_answer",
]
