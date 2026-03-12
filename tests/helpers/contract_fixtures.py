"""Contract test fixtures — layout and page template setup."""

from pathlib import Path


def write_layout_page(
    tmp_path: Path,
    layout: str,
    page: str,
    *,
    layout_name: str = "_layout.html",
    page_name: str = "page.html",
    encoding: str = "utf-8",
    extra: dict[str, str] | None = None,
) -> None:
    """Write layout and page templates for contract tests.

    Args:
        tmp_path: Pytest tmp_path fixture (project template dir).
        layout: Content for the layout template.
        page: Content for the page template.
        layout_name: Layout filename (default ``_layout.html``).
        page_name: Page filename (default ``page.html``).
        encoding: File encoding (default ``utf-8``).
        extra: Additional files as ``{filename: content}`` (e.g.
            ``{"_page_layout.html": "..."}``).
    """
    (tmp_path / layout_name).write_text(layout, encoding=encoding)
    (tmp_path / page_name).write_text(page, encoding=encoding)
    for filename, content in (extra or {}).items():
        (tmp_path / filename).write_text(content, encoding=encoding)
