from chirp import Page


def get(project: dict[str, str], slug: str) -> Page:
    return Page(
        "projects/{slug}/settings/page.html",
        "page_content",
        page_block_name="page_root",
        project=project,
        slug=slug,
    )
