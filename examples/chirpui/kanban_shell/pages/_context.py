"""Root context for kanban_shell — columns, shell_actions, current_user."""

from store import COLUMNS

from chirp import ShellAction, ShellActions, ShellActionZone, get_user


def context() -> dict:
    user = get_user()
    return {
        "columns": COLUMNS,
        "shell_actions": ShellActions(
            primary=ShellActionZone(
                items=(ShellAction(id="new-task", label="New task", action="new-task", variant="primary", icon="add"),)
            ),
            overflow=ShellActionZone(
                items=(ShellAction(id="filter", label="Filter", href="#board"),)
            ),
        ),
        "current_user": user,
    }
