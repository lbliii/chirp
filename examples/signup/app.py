"""Signup — registration form with validation and CSRF protection.

Demonstrates chirp's form validation system: ``validate()`` with built-in
rules, custom validators, ``CSRFMiddleware`` for token protection, and
``ValidationError`` for re-rendering forms with per-field errors.

Credentials are stored in memory — this is a demo, not production auth.

Demonstrates:
- ``validate()`` with ``required``, ``min_length``, ``max_length``, ``email``, ``matches``
- Custom validator (password confirmation)
- ``CSRFMiddleware`` + ``SessionMiddleware``
- ``csrf_field()`` template global
- ``ValidationError`` for 422 form re-render
- ``Redirect`` on success

Run:
    python app.py
"""

from pathlib import Path

from chirp import App, AppConfig, Redirect, Request, Template, ValidationError
from chirp.middleware.csrf import CSRFConfig, CSRFMiddleware, csrf_field
from chirp.middleware.sessions import SessionConfig, SessionMiddleware, get_session
from chirp.validation import Validator, email, matches, max_length, min_length, required, validate

TEMPLATES_DIR = Path(__file__).parent / "templates"

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------

config = AppConfig(template_dir=TEMPLATES_DIR)
app = App(config=config)

app.add_middleware(SessionMiddleware(SessionConfig(secret_key="change-me-in-production")))
app.add_middleware(CSRFMiddleware(CSRFConfig()))

# Register CSRF template global
app.template_global("csrf_field")(csrf_field)

# ---------------------------------------------------------------------------
# In-memory "database"
# ---------------------------------------------------------------------------

_users: list[dict[str, str]] = []

# ---------------------------------------------------------------------------
# Custom validator — password confirmation
# ---------------------------------------------------------------------------

_username_pattern = matches(
    r"^[a-zA-Z0-9_]+$",
    message="Only letters, numbers, and underscores allowed",
)


def _passwords_match(confirm: str, form_data: dict[str, str]) -> Validator:
    """Return a validator that checks if confirm matches the password field."""
    password = form_data.get("password", "")

    def check(value: str) -> str | None:
        if value != password:
            return "Passwords do not match"
        return None

    return check


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.route("/")
def index():
    """Redirect to the signup form."""
    return Redirect("/signup")


@app.route("/signup")
def signup_page():
    """Show the registration form."""
    return Template("signup.html")


@app.route("/signup", methods=["POST"])
async def do_signup(request: Request):
    """Handle registration form submission."""
    form = await request.form()

    # Build form dict for re-rendering and custom validators
    form_values = {
        "username": form.get("username", ""),
        "email": form.get("email", ""),
        "password": form.get("password", ""),
        "confirm_password": form.get("confirm_password", ""),
    }

    # Validate with built-in + custom rules
    result = validate(form, {
        "username": [required, min_length(3), max_length(30), _username_pattern],
        "email": [required, email],
        "password": [required, min_length(8), max_length(128)],
        "confirm_password": [required, _passwords_match(form_values["confirm_password"], form_values)],
    })

    if not result:
        return ValidationError(
            "signup.html", "signup_form",
            errors=result.errors,
            form=form_values,
        )

    # Check for duplicate username
    for user in _users:
        if user["username"] == form_values["username"]:
            return ValidationError(
                "signup.html", "signup_form",
                errors={"username": ["This username is already taken"]},
                form=form_values,
            )

    # "Register" the user
    _users.append({"username": form_values["username"], "email": form_values["email"]})

    # Store name in session for the welcome page
    session = get_session()
    session["username"] = form_values["username"]

    return Redirect("/welcome")


@app.route("/welcome")
def welcome():
    """Show the welcome page after registration."""
    session = get_session()
    username = session.get("username", "friend")
    return Template("welcome.html", username=username)


if __name__ == "__main__":
    app.run()
