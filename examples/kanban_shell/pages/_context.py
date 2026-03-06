"""Root context for kanban_shell — columns, shell_actions, current_user."""

from chirp import ShellAction, ShellActions, ShellActionZone, get_user

from store import COLUMNS


def context() -> dict:
    user = get_user()
    return {
        "columns": COLUMNS,
        "shell_actions": ShellActions(
            primary=ShellActionZone(
                items=(ShellAction(id="new-task", label="New task", href="#add-form"),)
            ),
            overflow=ShellActionZone(
                items=(ShellAction(id="filter", label="Filter", href="#board"),)
            ),
        ),
        "current_user": user,
    }
