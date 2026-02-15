"""Accessibility — feedback form with semantic HTML and ARIA patterns.

Demonstrates the accessibility guide in practice: semantic structure,
skip link, label/input association, aria-describedby, aria-invalid,
aria-live for dynamic content, and visible focus styles.

Run:
    cd examples/accessibility && python app.py
"""

from pathlib import Path

from chirp import App, AppConfig, Request, Template, ValidationError
from chirp.validation import required, validate

TEMPLATES_DIR = Path(__file__).parent / "templates"

config = AppConfig(template_dir=TEMPLATES_DIR)
app = App(config=config)


@app.route("/")
def index():
    """Show the feedback form."""
    return Template("index.html")


@app.route("/feedback", methods=["POST"])
async def feedback(request: Request):
    """Handle feedback form submission."""
    form = await request.form()
    result = validate(form, {
        "name": [required],
        "message": [required],
    })

    if not result:
        return ValidationError(
            "index.html",
            "feedback_form",
            errors=result.errors,
            form={
                "name": form.get("name", ""),
                "message": form.get("message", ""),
            },
        )

    return Template(
        "index.html",
        success=True,
        name=form.get("name", ""),
    )


if __name__ == "__main__":
    app.run()
