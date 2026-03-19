from chirp import ShellAction, ShellActions, ShellActionZone


def context() -> dict[str, object]:
    return {
        "shell_actions": ShellActions(
            primary=ShellActionZone(
                items=(
                    ShellAction(
                        id="new-contact",
                        label="New contact",
                        action="new-contact",
                        variant="primary",
                        icon="add",
                    ),
                )
            ),
            overflow=ShellActionZone(
                items=(ShellAction(id="clear-search", label="Clear filters", href="/contacts"),)
            ),
        )
    }
