from chirp import Page


def get(project: dict[str, str], slug: str) -> Page:
    return Page.mounted(
        "projects/{slug}/settings/page.html",
        project=project,
        slug=slug,
    )
