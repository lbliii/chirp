from chirp import Page


def get(projects: tuple[dict[str, str], ...]) -> Page:
    return Page(
        "projects/page.html",
        "page_content",
        page_block_name="page_root",
        projects=projects,
    )
