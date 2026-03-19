"""Board page handler — GET /."""

from store import get_tasks, tasks_by_column

from chirp import Page, Redirect, get_user


def get(request, columns) -> Page | Redirect:
    user = get_user()
    if not user.is_authenticated:
        next_url = request.query.get("next", "/")
        return Redirect(f"/login?next={next_url}")

    tasks = get_tasks()
    priority_filter = request.query.get_list("priority")
    assignee_filter = request.query.get_list("assignee")
    tag_filter = request.query.get_list("tag")

    if priority_filter:
        tasks = [t for t in tasks if t.priority in priority_filter]
    if assignee_filter:
        tasks = [t for t in tasks if t.assignee in assignee_filter]
    if tag_filter:
        tag_set = set(tag_filter)
        tasks = [t for t in tasks if tag_set & set(t.tags)]

    board = tasks_by_column(tasks)
    active_filters = {
        "priority": priority_filter,
        "assignee": assignee_filter,
        "tag": tag_filter,
    }

    return Page(
        "page.html",
        "page_content",
        page_block_name="page_root",
        board=board,
        columns=columns,
        all_tasks=get_tasks(),
        active_filters=active_filters,
    )
