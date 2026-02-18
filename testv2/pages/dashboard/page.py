from chirp import Template, get_user, login_required


_GRID_COLUMNS = [{"key": "name", "label": "Name"}, {"key": "role", "label": "Role"}]


@login_required
async def handler():
    return Template("dashboard/page.html", user=get_user(), cols=_GRID_COLUMNS)
