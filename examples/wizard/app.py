"""Wizard — multi-step checkout form with session persistence.

Demonstrates a multi-page form flow where data persists across steps
using session middleware. Each step validates independently, and the
final review page reads back all collected data before confirmation.

Demonstrates:
- ``SessionMiddleware`` + ``get_session()`` to persist data between steps
- ``validate()`` on each step independently
- ``Redirect`` between steps
- Session read-back for review page
- Session cleanup on completion
- Step navigation (back/next) preserving data

Run:
    python app.py
"""

import os
from pathlib import Path

from chirp import App, AppConfig, Redirect, Request, Template, ValidationError
from chirp.middleware.sessions import SessionConfig, SessionMiddleware, get_session
from chirp.validation import email, matches, max_length, min_length, required, validate

TEMPLATES_DIR = Path(__file__).parent / "templates"

config = AppConfig(template_dir=TEMPLATES_DIR)
app = App(config=config)

_secret = os.environ.get("SESSION_SECRET_KEY", "dev-only-not-for-production")

app.add_middleware(SessionMiddleware(SessionConfig(secret_key=_secret)))

# ---------------------------------------------------------------------------
# Session keys
# ---------------------------------------------------------------------------

_SESSION_KEY = "wizard_data"

_US_ZIP = matches(r"^\d{5}(-\d{4})?$", message="Must be a valid US zip code (e.g. 90210)")


def _get_wizard_data() -> dict:
    """Get the wizard form data from the session."""
    session = get_session()
    return session.get(_SESSION_KEY, {})


def _set_wizard_data(data: dict) -> None:
    """Store wizard form data in the session."""
    session = get_session()
    session[_SESSION_KEY] = data


def _clear_wizard_data() -> None:
    """Remove wizard data from the session."""
    session = get_session()
    session.pop(_SESSION_KEY, None)


# ---------------------------------------------------------------------------
# Routes — Step 1: Personal Info
# ---------------------------------------------------------------------------


@app.route("/")
def index():
    """Redirect to step 1."""
    return Redirect("/step/1")


@app.route("/step/1")
def step1():
    """Show personal info form (step 1)."""
    data = _get_wizard_data()
    return Template("step1.html", form=data, step=1)


@app.route("/step/1", methods=["POST"])
async def step1_submit(request: Request):
    """Validate and save personal info, advance to step 2."""
    form = await request.form()
    data = _get_wizard_data()

    form_values = {
        "first_name": form.get("first_name", ""),
        "last_name": form.get("last_name", ""),
        "email": form.get("email", ""),
        "phone": form.get("phone", ""),
    }

    result = validate(
        form,
        {
            "first_name": [required, max_length(50)],
            "last_name": [required, max_length(50)],
            "email": [required, email],
            "phone": [max_length(20)],
        },
    )

    if not result:
        return ValidationError(
            "step1.html",
            "step_form",
            errors=result.errors,
            form={**data, **form_values},
            step=1,
        )

    # Merge into session data and advance
    data.update(form_values)
    _set_wizard_data(data)
    return Redirect("/step/2")


# ---------------------------------------------------------------------------
# Routes — Step 2: Shipping Address
# ---------------------------------------------------------------------------


@app.route("/step/2")
def step2():
    """Show shipping address form (step 2)."""
    data = _get_wizard_data()
    # Require step 1 to be completed
    if not data.get("first_name"):
        return Redirect("/step/1")
    return Template("step2.html", form=data, step=2)


@app.route("/step/2", methods=["POST"])
async def step2_submit(request: Request):
    """Validate and save shipping address, advance to step 3."""
    form = await request.form()
    data = _get_wizard_data()

    form_values = {
        "address": form.get("address", ""),
        "city": form.get("city", ""),
        "state": form.get("state", ""),
        "zip_code": form.get("zip_code", ""),
    }

    result = validate(
        form,
        {
            "address": [required, max_length(200)],
            "city": [required, max_length(100)],
            "state": [required, min_length(2), max_length(2)],
            "zip_code": [required, _US_ZIP],
        },
    )

    if not result:
        return ValidationError(
            "step2.html",
            "step_form",
            errors=result.errors,
            form={**data, **form_values},
            step=2,
        )

    data.update(form_values)
    _set_wizard_data(data)
    return Redirect("/step/3")


# ---------------------------------------------------------------------------
# Routes — Step 3: Review & Confirm
# ---------------------------------------------------------------------------


@app.route("/step/3")
def step3():
    """Show review page (step 3)."""
    data = _get_wizard_data()
    # Require steps 1 and 2 to be completed
    if not data.get("first_name"):
        return Redirect("/step/1")
    if not data.get("address"):
        return Redirect("/step/2")
    return Template("step3.html", form=data, step=3)


@app.route("/confirm", methods=["POST"])
def confirm():
    """Process the order and show confirmation."""
    data = _get_wizard_data()
    if not data.get("first_name") or not data.get("address"):
        return Redirect("/step/1")

    # "Place the order" — in a real app this would hit a payment API
    order_data = dict(data)
    _clear_wizard_data()

    return Template("confirmation.html", order=order_data)


if __name__ == "__main__":
    app.run()
