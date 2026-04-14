"""Simple keyword search over documentation pages.

No external dependencies.  Ranks results by weighted keyword frequency:
title matches score higher than body matches.
"""

from __future__ import annotations

from chirp.docs.models import DocPage

_TITLE_WEIGHT = 3
_BODY_WEIGHT = 1


def keyword_search(
    pages: tuple[DocPage, ...],
    query: str,
) -> tuple[DocPage, ...]:
    """Return pages matching *query*, ranked by relevance.

    Matching is case-insensitive.  Each whitespace-separated token in
    *query* is searched independently — a page must contain **all**
    tokens to match (AND semantics).

    Ranking: each token occurrence in the title scores 3 points, each
    occurrence in the raw body scores 1 point.
    """
    if not query or not query.strip():
        return ()

    tokens = query.lower().split()
    scored: list[tuple[float, DocPage]] = []

    for page in pages:
        if page.metadata.draft:
            continue
        title_lower = page.title.lower()
        body_lower = page.raw.lower()

        # All tokens must appear somewhere (AND)
        if not all(t in title_lower or t in body_lower for t in tokens):
            continue

        score = 0.0
        for t in tokens:
            score += title_lower.count(t) * _TITLE_WEIGHT
            score += body_lower.count(t) * _BODY_WEIGHT

        scored.append((score, page))

    scored.sort(key=lambda sp: sp[0], reverse=True)
    return tuple(page for _, page in scored)
