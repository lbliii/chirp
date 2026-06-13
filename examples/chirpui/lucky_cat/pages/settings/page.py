"""Settings room — GET /settings (#231 stub).

Thin room stub. Settings is also the destination of the topbar's `controls`
ShellAction (#230), so this route makes that affordance resolve to a real page.
"""

from chirp import Page


def get() -> Page:
    return Page("settings/page.html", "page_content", page_block_name="page_root")
