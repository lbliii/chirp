"""Auth — session login with protected routes.

The most basic authentication example: a login form, a protected
dashboard, and logout.  Uses an in-memory user with hardcoded
credentials (admin / password) and password hashing.

Demonstrates:
- SessionMiddleware + AuthMiddleware setup
- ``login()`` / ``logout()`` helpers
- ``@login_required`` decorator
- ``current_user()`` template global
- ``hash_password`` / ``verify_password``

Run:
    python app.py
"""

from dataclasses import dataclass
from pathlib import Path

from chirp import App, AppConfig, Redirect, Request, Template, get_user, login, login_required, logout
from chirp.middleware.auth import AuthConfig, AuthMiddleware
from chirp.middleware.sessions import SessionConfig, SessionMiddleware
from chirp.security.passwords import hash_password, verify_password

TEMPLATES_DIR = Path(__file__).parent / "templates"

# ---------------------------------------------------------------------------
# User model + in-memory "database"
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class User:
    """Minimal user model — satisfies chirp's User protocol."""

    id: str
    name: str
    password_hash: str
    is_authenticated: bool = True


# Pre-hash the demo password so verify_password works correctly
_DEMO_HASH = hash_password("password")

USERS: dict[str, User] = {
    "admin": User(id="admin", name="Admin", password_hash=_DEMO_HASH),
}


async def load_user(user_id: str) -> User | None:
    """Load a user by ID — called by AuthMiddleware on each request."""
    return USERS.get(user_id)


# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------

config = AppConfig(template_dir=TEMPLATES_DIR)
app = App(config=config)

app.add_middleware(SessionMiddleware(SessionConfig(secret_key="change-me-in-production")))
app.add_middleware(AuthMiddleware(AuthConfig(load_user=load_user)))

# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.route("/")
def index():
    """Public home page."""
    return Template("index.html")


@app.route("/login")
def login_page():
    """Show the login form."""
    return Template("login.html", error="")


@app.route("/login", methods=["POST"])
async def do_login(request: Request):
    """Handle login form submission."""
    form = await request.form()
    username = form.get("username", "")
    password = form.get("password", "")

    user = USERS.get(username)
    if user and verify_password(password, user.password_hash):
        login(user)
        return Redirect("/dashboard")

    return Template("login.html", error="Invalid username or password")


@app.route("/dashboard")
@login_required
def dashboard():
    """Protected page — only for logged-in users."""
    user = get_user()
    return Template("dashboard.html", user=user)


@app.route("/logout", methods=["POST"])
def do_logout():
    """Log out and redirect home."""
    logout()
    return Redirect("/")


if __name__ == "__main__":
    app.run()
