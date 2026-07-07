"""Testing helpers for compiled-transition runtime evidence."""

from __future__ import annotations

import base64
import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any, cast

from chirp.http.response import Response
from chirp.testing.sse import SSETestResult

_KNOWN_MODES = frozenset(
    {"normal", "boosted", "targeted", "htmx", "mutation", "oob", "suspense", "sse"}
)


@dataclass(frozen=True, slots=True)
class TransitionObservation:
    """One debug response correlated to compiled application transitions."""

    observation_id: str
    route_id: str
    route_path: str
    request_mode: str
    mode_tags: tuple[str, ...]
    compiled_transition_ids: tuple[str, ...]
    transition_descriptions: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class TransitionCoverage:
    """Observed runtime evidence and explicitly expected gaps."""

    observations: tuple[TransitionObservation, ...]
    observed_modes: tuple[str, ...]
    untested_modes: tuple[str, ...]
    observed_transition_ids: tuple[str, ...]
    unexercised_transition_ids: tuple[str, ...]

    @property
    def complete(self) -> bool:
        """Whether all caller-declared modes and transitions were observed."""
        return not self.untested_modes and not self.unexercised_transition_ids

    def summary(self) -> str:
        """Return an actionable compact coverage summary."""
        lines = [
            f"Observed {len(self.observations)} render transition(s) "
            f"across modes: {', '.join(self.observed_modes) or '(none)'}."
        ]
        if self.untested_modes:
            lines.append(f"Untested request modes: {', '.join(self.untested_modes)}.")
        if self.unexercised_transition_ids:
            lines.append(
                "Unexercised compiled transitions: "
                + ", ".join(self.unexercised_transition_ids)
                + "."
            )
        if self.complete:
            lines.append("All declared transition evidence is covered.")
        return "\n".join(lines)


type TraceResponse = Response | SSETestResult


def _decode_trace(response: TraceResponse) -> dict[str, Any]:
    if isinstance(response, Response):
        encoded = response.header("X-Chirp-Return-Trace")
    else:
        encoded = response.headers.get("x-chirp-return-trace")
    if encoded is None:
        msg = (
            "Response has no X-Chirp-Return-Trace header. "
            "Run the app with AppConfig(debug=True) and exercise a typed Chirp return."
        )
        raise ValueError(msg)
    try:
        raw = base64.b64decode(encoded, validate=True).decode("utf-8")
        payload = json.loads(raw)
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        msg = "Response has a malformed X-Chirp-Return-Trace header."
        raise ValueError(msg) from exc
    if not isinstance(payload, dict):
        msg = "X-Chirp-Return-Trace must decode to an object."
        raise TypeError(msg)
    return payload


def transition_observation(response: TraceResponse) -> TransitionObservation:
    """Read compiled transition evidence from one debug response."""
    payload = _decode_trace(response)
    required = ("observation_id", "route_id", "route_path", "request_mode")
    missing = [name for name in required if not payload.get(name)]
    if missing:
        msg = (
            "Return trace is not correlated to the compiled application; missing "
            + ", ".join(missing)
            + ". Ensure the response came through the frozen App runtime in debug mode."
        )
        raise ValueError(msg)
    return TransitionObservation(
        observation_id=str(payload["observation_id"]),
        route_id=str(payload["route_id"]),
        route_path=str(payload["route_path"]),
        request_mode=str(payload["request_mode"]),
        mode_tags=tuple(str(value) for value in payload.get("mode_tags", ())),
        compiled_transition_ids=tuple(
            str(value) for value in payload.get("compiled_transition_ids", ())
        ),
        transition_descriptions=tuple(
            str(value) for value in payload.get("transition_descriptions", ())
        ),
    )


def transition_coverage(
    responses: Iterable[TraceResponse] | Mapping[Any, TraceResponse],
    *,
    expected_modes: Iterable[str] = (),
    expected_transition_ids: Iterable[str] = (),
) -> TransitionCoverage:
    """Report observed and explicitly untested transition evidence.

    Expected values are caller declarations. Chirp does not infer that a
    static route has been behaviorally exercised in every browser mode.
    """
    if isinstance(responses, Mapping):
        values = cast("Mapping[Any, TraceResponse]", responses).values()
    else:
        values = cast("Iterable[TraceResponse]", responses)
    observations_by_id: dict[str, TransitionObservation] = {}
    for response in values:
        observation = transition_observation(response)
        observations_by_id[observation.observation_id] = observation
    observations = tuple(observations_by_id[key] for key in sorted(observations_by_id))

    observed_modes = tuple(sorted({tag for item in observations for tag in item.mode_tags}))
    expected_mode_set = {str(mode) for mode in expected_modes}
    unknown = sorted(expected_mode_set - _KNOWN_MODES)
    if unknown:
        msg = (
            f"Unknown transition mode(s): {', '.join(unknown)}. "
            f"Expected one of: {', '.join(sorted(_KNOWN_MODES))}."
        )
        raise ValueError(msg)
    observed_mode_set = set(observed_modes)
    untested_modes = tuple(sorted(expected_mode_set - observed_mode_set))

    observed_transition_ids = tuple(
        sorted({value for item in observations for value in item.compiled_transition_ids})
    )
    expected_ids = {str(value) for value in expected_transition_ids}
    unexercised = tuple(sorted(expected_ids - set(observed_transition_ids)))
    return TransitionCoverage(
        observations=observations,
        observed_modes=observed_modes,
        untested_modes=untested_modes,
        observed_transition_ids=observed_transition_ids,
        unexercised_transition_ids=unexercised,
    )
