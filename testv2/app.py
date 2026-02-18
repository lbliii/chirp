import chirp_ui
from models import load_user, verify_user

from chirp import (
    App,
    AppConfig,
    EventStream,
    Fragment,
    Redirect,
    Request,
    is_safe_url,
    login,
    logout,
    use_chirp_ui,
)
from chirp.middleware.auth import AuthConfig, AuthMiddleware
from chirp.middleware.csrf import CSRFConfig, CSRFMiddleware
from chirp.middleware.security_headers import SecurityHeadersMiddleware
from chirp.middleware.sessions import SessionConfig, SessionMiddleware

config = AppConfig(
    secret_key="change-me-before-deploying",
    template_dir="pages",
    islands=True,
)
app = App(config=config)

app.add_middleware(SessionMiddleware(SessionConfig(secret_key=config.secret_key)))
app.add_middleware(AuthMiddleware(AuthConfig(load_user=load_user)))
app.add_middleware(CSRFMiddleware(CSRFConfig()))
app.add_middleware(SecurityHeadersMiddleware())

use_chirp_ui(app)
chirp_ui.register_filters(app)

app.mount_pages("pages")


@app.route("/login", methods=["POST"])
async def do_login(request: Request):
    form = await request.form()
    username = form.get("username", "")
    password = form.get("password", "")
    user = verify_user(username, password)
    if user:
        login(user)
        next_url = request.query.get("next", "/dashboard")
        return Redirect(next_url if is_safe_url(next_url) else "/dashboard")
    return Redirect("/login?error=1")


@app.route("/logout", methods=["POST"])
def do_logout():
    logout()
    return Redirect("/")


@app.route("/time", referenced=True)
async def time_stream(request: Request) -> EventStream:
    import asyncio
    from datetime import datetime

    async def events():
        while True:
            yield Fragment("dashboard/page.html", "time_block", now=datetime.now().isoformat())
            await asyncio.sleep(1)

    return EventStream(events())


if __name__ == "__main__":
    app.run()
