from chirp import ShellAction, ShellActions, ShellActionZone

PROJECTS = (
    {
        "slug": "apollo",
        "name": "Apollo",
        "summary": "Migrate the control plane to mounted pages and shell actions.",
        "status": "shipping",
        "owner": "Platform",
    },
    {
        "slug": "beacon",
        "name": "Beacon",
        "summary": "Add live search, history-safe fragments, and request tracing.",
        "status": "active",
        "owner": "DX",
    },
    {
        "slug": "cosmos",
        "name": "Cosmos",
        "summary": "Prototype layout-chain suspense for a nested dashboard.",
        "status": "exploring",
        "owner": "Infra",
    },
)


def context() -> dict:
    return {
        "projects": PROJECTS,
        "shell_actions": ShellActions(
            primary=ShellActionZone(
                items=(ShellAction(id="new-project", label="New project", href="/projects"),)
            ),
            overflow=ShellActionZone(
                items=(
                    ShellAction(id="docs", label="Routing docs", href="/projects"),
                    ShellAction(id="archive", label="Archive", href="/projects", icon="archive"),
                    ShellAction(id="export", label="Export", href="/projects", icon="export"),
                ),
            ),
        ),
    }
