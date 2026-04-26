from chirp import Page


def get(projects: tuple[dict[str, str], ...]) -> Page:
    return Page.mounted(
        "projects/page.html",
        projects=projects,
    )
