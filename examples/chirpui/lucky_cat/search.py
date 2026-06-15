"""The one substring matcher for Lucky Cat (#277).

Both the Cmd/Ctrl-K command palette (:mod:`command_palette`) and the Research
power surface (``pages/markets/research``) narrow lists by the same rule, so the
quick-jump and the full catalog can never drift on *what counts as a match*.
That rule lives here, once.

Pure Python, no I/O — mirrors :mod:`navigation` / :mod:`command_palette`.
"""

from __future__ import annotations


def matches(query: str, *haystacks: str) -> bool:
    """True when **every** whitespace-separated query token is a substring of at
    least one haystack (case-insensitive). An empty / whitespace query matches
    everything (the resting palette and the unfiltered catalog).

    Token-AND, substring-per-token: ``"bt me"`` matches ``"BTC-MEOW"`` because
    both ``bt`` and ``me`` appear in the joined haystack, but ``"xrp"`` does not.
    """
    q = query.strip().lower()
    if not q:
        return True
    hay = " ".join(haystacks).lower()
    return all(token in hay for token in q.split())
