"""Utility helpers shared by contract rules."""


def edit_distance(a: str, b: str) -> int:
    """Levenshtein distance between two strings."""
    if len(a) > len(b):
        a, b = b, a
    prev = list(range(len(a) + 1))
    for j in range(1, len(b) + 1):
        curr = [j] + [0] * len(a)
        for i in range(1, len(a) + 1):
            cost = 0 if a[i - 1] == b[j - 1] else 1
            curr[i] = min(curr[i - 1] + 1, prev[i] + 1, prev[i - 1] + cost)
        prev = curr
    return prev[len(a)]


def closest_match(target: str, values: set[str], *, max_dist: int) -> str | None:
    """Return closest string within max_dist, or None."""
    if not values:
        return None
    best: str | None = None
    best_dist = max_dist + 1
    for candidate in sorted(values):
        dist = edit_distance(target, candidate)
        if dist < best_dist:
            best_dist = dist
            best = candidate
    return best if best_dist <= max_dist else None


def closest_id(target: str, ids: set[str], *, max_dist: int = 3) -> str | None:
    """Closest ID match ignoring case."""
    lower_ids = {value.lower(): value for value in ids}
    best = closest_match(target.lower(), set(lower_ids), max_dist=max_dist)
    if best is None:
        return None
    return lower_ids[best]


def closest_field(target: str, fields: set[str], *, max_dist: int = 2) -> str | None:
    """Closest form field candidate."""
    return closest_match(target, fields, max_dist=max_dist)
