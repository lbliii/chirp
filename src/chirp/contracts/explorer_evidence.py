"""Private runtime-evidence overlay for the Contract Explorer.

The overlay copies only allowlisted identity and timing metadata from one
bounded debug/test capture snapshot.  It never receives an ``App``, allocates
a capture store, or changes the static compiler/check projection.  Production
callers represent the absence of a debug capture with ``None``.

Evidence is process-local and lifecycle-local.  Counts describe only the
retained response observations in the supplied snapshot; truncation, stale
topology identities, and observations without stable identities remain
explicit rather than being interpreted as contract truth.

This module is internal and is not exported from :mod:`chirp` or
:mod:`chirp.contracts`.  Its records are not a public telemetry schema.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from chirp.server.intent_timeline import _CaptureSnapshot, _ResponseObservation

from .explorer_projection import ExplorerProjection

type ExplorerEvidenceCaptureState = Literal["active", "closed", "unavailable"]
type ExplorerObservationState = Literal["matched", "stale", "unknown"]


@dataclass(frozen=True, slots=True)
class ExplorerEvidenceCapture:
    """Retention and lifecycle facts for the supplied capture snapshot."""

    state: ExplorerEvidenceCaptureState
    retained_observation_count: int
    response_observation_count: int
    retained_bytes: int
    truncated: bool
    dropped_count: int
    first_retained_sequence: int | None


@dataclass(frozen=True, slots=True)
class ExplorerRuntimeEvidence:
    """One retained response correlated only through stable private IDs."""

    sequence: int
    elapsed_us: int
    observation_id: str | None
    route_id: str | None
    request_mode: str | None
    state: ExplorerObservationState
    matched_transition_ids: tuple[str, ...]
    unmatched_transition_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ExplorerTransitionEvidence:
    """Bounded aggregate for one transition in the static projection."""

    transition_id: str
    count: int
    first_observed_sequence: int
    last_observed_sequence: int
    last_observed_elapsed_us: int
    last_observation_id: str | None
    last_route_id: str | None
    last_request_mode: str | None


@dataclass(frozen=True, slots=True)
class ExplorerEvidenceOverlay:
    """Static topology plus visibly separate retained runtime evidence."""

    topology: ExplorerProjection
    capture: ExplorerEvidenceCapture
    observations: tuple[ExplorerRuntimeEvidence, ...]
    transitions: tuple[ExplorerTransitionEvidence, ...]
    unmatched_observations: tuple[ExplorerRuntimeEvidence, ...]


@dataclass(slots=True)
class _TransitionAccumulator:
    count: int
    first_observed_sequence: int
    last_observed_sequence: int
    last_observed_elapsed_us: int
    last_observation_id: str | None
    last_route_id: str | None
    last_request_mode: str | None


def overlay_explorer_evidence(
    topology: ExplorerProjection,
    snapshot: _CaptureSnapshot | None,
) -> ExplorerEvidenceOverlay:
    """Overlay one immutable capture snapshot without redefining topology."""
    if snapshot is None:
        return ExplorerEvidenceOverlay(
            topology=topology,
            capture=ExplorerEvidenceCapture(
                state="unavailable",
                retained_observation_count=0,
                response_observation_count=0,
                retained_bytes=0,
                truncated=False,
                dropped_count=0,
                first_retained_sequence=None,
            ),
            observations=(),
            transitions=(),
            unmatched_observations=(),
        )

    route_ids = {node.id for node in topology.nodes if node.kind == "route"}
    transition_ids = {edge.id for edge in topology.edges}
    observations: list[ExplorerRuntimeEvidence] = []
    accumulators: dict[str, _TransitionAccumulator] = {}

    for captured in snapshot.observations:
        detail = captured.detail
        if captured.internal:
            continue
        if captured.channel != "http" or captured.phase != "response":
            continue
        if not isinstance(detail, _ResponseObservation):
            continue

        supplied_transition_ids = tuple(dict.fromkeys(detail.compiled_transition_ids))
        matched_transition_ids = tuple(
            transition_id
            for transition_id in supplied_transition_ids
            if transition_id in transition_ids
        )
        unmatched_transition_ids = tuple(
            transition_id
            for transition_id in supplied_transition_ids
            if transition_id not in transition_ids
        )
        route_is_stale = detail.route_id is not None and detail.route_id not in route_ids
        has_identity = detail.route_id is not None or bool(supplied_transition_ids)
        state: ExplorerObservationState
        if not has_identity:
            state = "unknown"
        elif route_is_stale or unmatched_transition_ids:
            state = "stale"
        else:
            state = "matched"

        evidence = ExplorerRuntimeEvidence(
            sequence=captured.sequence,
            elapsed_us=captured.elapsed_us,
            observation_id=detail.observation_id,
            route_id=detail.route_id,
            request_mode=detail.request_mode,
            state=state,
            matched_transition_ids=matched_transition_ids,
            unmatched_transition_ids=unmatched_transition_ids,
        )
        observations.append(evidence)
        for transition_id in matched_transition_ids:
            accumulator = accumulators.get(transition_id)
            if accumulator is None:
                accumulators[transition_id] = _TransitionAccumulator(
                    count=1,
                    first_observed_sequence=captured.sequence,
                    last_observed_sequence=captured.sequence,
                    last_observed_elapsed_us=captured.elapsed_us,
                    last_observation_id=detail.observation_id,
                    last_route_id=detail.route_id,
                    last_request_mode=detail.request_mode,
                )
                continue
            accumulator.count += 1
            accumulator.last_observed_sequence = captured.sequence
            accumulator.last_observed_elapsed_us = captured.elapsed_us
            accumulator.last_observation_id = detail.observation_id
            accumulator.last_route_id = detail.route_id
            accumulator.last_request_mode = detail.request_mode

    projected_observations = tuple(observations)
    marker = snapshot.truncation
    return ExplorerEvidenceOverlay(
        topology=topology,
        capture=ExplorerEvidenceCapture(
            state="active" if snapshot.active else "closed",
            retained_observation_count=len(snapshot.observations),
            response_observation_count=len(projected_observations),
            retained_bytes=snapshot.retained_bytes,
            truncated=marker is not None,
            dropped_count=marker.dropped_count if marker is not None else 0,
            first_retained_sequence=(
                marker.first_retained_sequence if marker is not None else None
            ),
        ),
        observations=projected_observations,
        transitions=tuple(
            ExplorerTransitionEvidence(
                transition_id=transition_id,
                count=accumulator.count,
                first_observed_sequence=accumulator.first_observed_sequence,
                last_observed_sequence=accumulator.last_observed_sequence,
                last_observed_elapsed_us=accumulator.last_observed_elapsed_us,
                last_observation_id=accumulator.last_observation_id,
                last_route_id=accumulator.last_route_id,
                last_request_mode=accumulator.last_request_mode,
            )
            for transition_id, accumulator in sorted(accumulators.items())
        ),
        unmatched_observations=tuple(
            observation for observation in projected_observations if observation.state != "matched"
        ),
    )
