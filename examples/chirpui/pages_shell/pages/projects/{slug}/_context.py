from chirp import NotFound, ShellAction, ShellActions, ShellActionZone


def context(slug: str, projects: tuple[dict[str, str], ...]) -> dict:
    project = next((item for item in projects if item["slug"] == slug), None)
    if project is None:
        raise NotFound(f"Project {slug!r} not found")

    return {
        "project": project,
        "shell_actions": ShellActions(
            primary=ShellActionZone(
                items=(ShellAction(id="deploy", label="Deploy", href=f"/projects/{slug}"),),
                remove=("new-project",),
            ),
            controls=ShellActionZone(
                items=(ShellAction(id="metrics", label="Metrics", href="#project-stats"),)
            ),
        ),
    }
