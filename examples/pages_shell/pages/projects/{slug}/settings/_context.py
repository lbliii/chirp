"""Settings subroute: replaces parent shell actions entirely (mode='replace').

Form pages often need different topbar actions (Save, Cancel) instead of
inheriting list/detail actions (New project, Deploy, Metrics).
"""

from chirp import ShellAction, ShellActions, ShellActionZone


def context(slug: str, project: dict[str, str]) -> dict:
    return {
        "project": project,
        "shell_actions": ShellActions(
            primary=ShellActionZone(
                items=(
                    ShellAction(id="save", label="Save", href=f"/projects/{slug}/settings", variant="primary"),
                    ShellAction(id="cancel", label="Cancel", href=f"/projects/{slug}"),
                ),
                mode="replace",
            ),
            controls=ShellActionZone(mode="replace"),
            overflow=ShellActionZone(mode="replace"),
        ),
    }
