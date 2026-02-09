"""Survey — multi-field form with checkboxes, radios, selects, and textarea.

Demonstrates every HTML form input type that chirp supports, including
multi-value fields via ``get_list()`` for checkbox groups.

Demonstrates:
- ``form.get_list("interests")`` for checkbox groups
- ``form.get("experience")`` for radio buttons
- ``validate()`` with ``required``, ``one_of``, ``integer``, and custom rules
- ``ValidationError`` with per-field error display
- Complex form with text, number, checkboxes, radios, select, textarea

Run:
    python app.py
"""

from pathlib import Path

from chirp import App, AppConfig, Request, Template, ValidationError
from chirp.validation import Validator, integer, max_length, one_of, required, validate

TEMPLATES_DIR = Path(__file__).parent / "templates"

config = AppConfig(template_dir=TEMPLATES_DIR)
app = App(config=config)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

INTERESTS = [
    ("coding", "Coding"),
    ("design", "Design"),
    ("music", "Music"),
    ("sports", "Sports"),
    ("travel", "Travel"),
    ("reading", "Reading"),
    ("cooking", "Cooking"),
    ("gaming", "Gaming"),
]

EXPERIENCE_LEVELS = [
    ("beginner", "Beginner (< 1 year)"),
    ("intermediate", "Intermediate (1–3 years)"),
    ("advanced", "Advanced (3–7 years)"),
    ("expert", "Expert (7+ years)"),
]

COUNTRIES = [
    ("", "Select a country..."),
    ("us", "United States"),
    ("gb", "United Kingdom"),
    ("ca", "Canada"),
    ("de", "Germany"),
    ("fr", "France"),
    ("jp", "Japan"),
    ("au", "Australia"),
    ("br", "Brazil"),
    ("other", "Other"),
]

# ---------------------------------------------------------------------------
# Custom validators
# ---------------------------------------------------------------------------


def _at_least_one_interest(value: str) -> str | None:
    """Placeholder — actual check uses get_list in the route."""
    return None


def _valid_age(value: str) -> str | None:
    """Age must be between 1 and 150."""
    try:
        age = int(value)
    except (ValueError, TypeError):
        return "Must be a whole number"
    if age < 1 or age > 150:
        return "Age must be between 1 and 150"
    return None


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.route("/")
def survey_form():
    """Show the survey form."""
    return Template(
        "survey.html",
        interests=INTERESTS,
        experience_levels=EXPERIENCE_LEVELS,
        countries=COUNTRIES,
    )


@app.route("/submit", methods=["POST"])
async def submit_survey(request: Request):
    """Handle survey submission with validation."""
    form = await request.form()

    # Collect form values for re-rendering
    form_values = {
        "name": form.get("name", ""),
        "age": form.get("age", ""),
        "experience": form.get("experience", ""),
        "country": form.get("country", ""),
        "comments": form.get("comments", ""),
    }
    selected_interests = form.get_list("interests")

    # Validate single-value fields
    result = validate(form, {
        "name": [required, max_length(100)],
        "age": [required, integer, _valid_age],
        "experience": [
            required,
            one_of("beginner", "intermediate", "advanced", "expert"),
        ],
        "country": [
            required,
            one_of("us", "gb", "ca", "de", "fr", "jp", "au", "br", "other"),
        ],
        "comments": [max_length(1000)],
    })

    errors = dict(result.errors) if not result else {}

    # Validate multi-value field (checkboxes)
    valid_interest_keys = {key for key, _ in INTERESTS}
    if not selected_interests:
        errors["interests"] = ["Please select at least one interest"]
    elif any(i not in valid_interest_keys for i in selected_interests):
        errors["interests"] = ["Invalid interest selected"]

    if errors:
        return ValidationError(
            "survey.html", "survey_form",
            errors=errors,
            form=form_values,
            selected_interests=selected_interests,
            interests=INTERESTS,
            experience_levels=EXPERIENCE_LEVELS,
            countries=COUNTRIES,
        )

    # Build display-friendly results
    interest_labels = [label for key, label in INTERESTS if key in selected_interests]
    experience_label = next(
        (label for key, label in EXPERIENCE_LEVELS if key == form_values["experience"]),
        form_values["experience"],
    )
    country_label = next(
        (label for key, label in COUNTRIES if key == form_values["country"]),
        form_values["country"],
    )

    return Template(
        "results.html",
        name=form_values["name"],
        age=form_values["age"],
        interests=interest_labels,
        experience=experience_label,
        country=country_label,
        comments=form_values["comments"],
    )


if __name__ == "__main__":
    app.run()
