"""Editor link support for debug page file:line URLs."""

import os

_EDITOR_PRESETS: dict[str, str] = {
    "vscode": "vscode://file/__FILE__:__LINE__",
    "cursor": "cursor://file/__FILE__:__LINE__",
    "sublime": "subl://open?url=file://__FILE__&line=__LINE__",
    "textmate": "txmt://open?url=file://__FILE__&line=__LINE__",
    "idea": "idea://open?file=__FILE__&line=__LINE__",
    "pycharm": "pycharm://open?file=__FILE__&line=__LINE__",
}


def _editor_url(filepath: str, lineno: int) -> str | None:
    """Build a clickable editor URL from CHIRP_EDITOR env var.

    Supports preset names (``vscode``, ``cursor``, ``sublime``, ``textmate``,
    ``idea``, ``pycharm``) or custom patterns with ``__FILE__`` / ``__LINE__``
    placeholders.

    Returns ``None`` if ``CHIRP_EDITOR`` is not set.
    """
    pattern = os.environ.get("CHIRP_EDITOR", "")
    if not pattern:
        return None
    # Resolve presets
    pattern = _EDITOR_PRESETS.get(pattern.lower(), pattern)
    return pattern.replace("__FILE__", filepath).replace("__LINE__", str(lineno))
