"""Stable DOM ids for Chirp *shell regions* (HTMX OOB targets).

Shell regions live **outside** ``#page-content``. They are updated via
``hx-swap-oob`` during fragment navigations, not by the primary ``#main`` swap.

**Vocabulary:** see the UI layers guide (``site/content/docs/guides/ui-layers.md``).

``SHELL_ACTIONS_TARGET`` is defined in ``chirp.shell_actions`` and re-exported
here so all shell ids live in one import path.
"""

from chirp.shell_actions import SHELL_ACTIONS_TARGET

DOCUMENT_TITLE_ELEMENT_ID = "chirpui-document-title"
ANNOUNCEMENTS_ELEMENT_ID = "chirp-announcements"
FOCUS_FALLBACK_DEFAULT = "#main"

#: Element ids that participate in the default Chirp shell OOB contract.
SHELL_ELEMENT_IDS: frozenset[str] = frozenset(
    {
        DOCUMENT_TITLE_ELEMENT_ID,
        SHELL_ACTIONS_TARGET,
        ANNOUNCEMENTS_ELEMENT_ID,
    }
)

__all__ = [
    "ANNOUNCEMENTS_ELEMENT_ID",
    "DOCUMENT_TITLE_ELEMENT_ID",
    "FOCUS_FALLBACK_DEFAULT",
    "SHELL_ACTIONS_TARGET",
    "SHELL_ELEMENT_IDS",
]
