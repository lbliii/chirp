"""Root context for recipe builder."""

from chirp import ShellActions


def context() -> dict:
    return {
        "shell_actions": ShellActions(),
    }
