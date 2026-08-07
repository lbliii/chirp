"""Shell action constants — shared by pages and templating without circular deps.

For all documented shell *region* element ids (including this target), see
``chirp.shell_regions``.
"""

from dataclasses import dataclass

SHELL_ACTIONS_CONTEXT_KEY = "shell_actions"
SHELL_ACTIONS_TARGET = "chirp-shell-actions"
SHELL_ACTIONS_TEMPLATE = "chirp/shell_actions.html"
SHELL_ACTIONS_BLOCK = "content"

#: Chirp-ui compatibility renderer — activated only by ``use_chirp_ui``.
SHELL_ACTIONS_CHIRPUI_TEMPLATE = "chirp/compat/shell_actions_chirpui.html"


@dataclass(frozen=True, slots=True)
class ShellActionsRenderer:
    """Template/block pair that renders shell actions for OOB transport.

    The transport contract (target id, OOB wrap, region updates) stays fixed.
    Applications override only the HTML renderer — never the swap plumbing.
    """

    template: str = SHELL_ACTIONS_TEMPLATE
    block: str = SHELL_ACTIONS_BLOCK


DEFAULT_SHELL_ACTIONS_RENDERER = ShellActionsRenderer()
