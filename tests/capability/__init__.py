"""Specialized CI capability-lane skip-fail policy (#917).

Opt a CI job into fail-on-unexpected-skip by setting::

    CHIRP_CAPABILITY_LANE=<lane-name>

Lane definitions live in ``tests.capability.lanes``. New specialized lanes
(e.g. redis-capability from #906) add a registry entry and set the env var on
their pytest step — no plugin rewrite required.
"""

from tests.capability.lanes import (
    CAPABILITY_LANE_ENV,
    LANE_REGISTRY,
    CapabilityLane,
    get_lane,
)

__all__ = [
    "CAPABILITY_LANE_ENV",
    "LANE_REGISTRY",
    "CapabilityLane",
    "get_lane",
]
