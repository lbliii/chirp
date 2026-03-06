"""Login page handler — GET/POST /login."""

from chirp import Page, Redirect, get_user, is_safe_url, login
from chirp.security.passwords import verify_password


def get(request) -> Page:
    if get_user().is_authenticated:
        return Redirect("/")
    from app import get_users
    next_url = request.query.get("next", "/")
    return Page("login/page.html", "page_content", error="", users=get_users(), next_url=next_url)


async def post(request) -> Page | Redirect:
    if get_user().is_authenticated:
        return Redirect("/")

    form = await request.form()
    username = form.get("username", "").strip().lower()
    password = form.get("password", "")
    next_url = form.get("next", "/")

    from app import get_users
    users = get_users()
    user = users.get(username)
    if user and verify_password(password, user.password_hash):
        login(user)
        if not is_safe_url(next_url):
            next_url = "/"
        return Redirect(next_url)
    return Page(
        "login/page.html",
        "page_content",
        error="Invalid username or password",
        users=users,
        next_url=next_url or "/",
    )
