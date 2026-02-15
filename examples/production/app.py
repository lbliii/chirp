"""Production — production-ready starter with full security stack.

Demonstrates the recommended middleware stack for production Chirp apps:
SecurityHeadersMiddleware, SessionMiddleware, CSRFMiddleware. A minimal
contact form shows CSRF protection and the url filter for user-supplied links.

Demonstrates:
- SecurityHeadersMiddleware (X-Frame-Options, X-Content-Type-Options, Referrer-Policy)
- SessionMiddleware + CSRFMiddleware + csrf_field()
- url filter for safe href rendering (website field)
- Template, Redirect, request.form()

Run:
    pip install chirp[sessions]
    cd examples/production && python app.py
"""

import os
from pathlib import Path

from chirp import App, AppConfig, Redirect, Request, Template
from chirp.middleware.csrf import CSRFConfig, CSRFMiddleware, csrf_field
from chirp.middleware.security_headers import SecurityHeadersMiddleware
from chirp.middleware.sessions import SessionConfig, SessionMiddleware, get_session

TEMPLATES_DIR = Path(__file__).parent / "templates"

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------

_secret = os.environ.get("SESSION_SECRET_KEY", "dev-only-not-for-production")
config = AppConfig(template_dir=TEMPLATES_DIR)
app = App(config=config)

# Order matters: SecurityHeaders wraps the response; Session/CSRF wrap the request
app.add_middleware(SecurityHeadersMiddleware())
app.add_middleware(SessionMiddleware(SessionConfig(secret_key=_secret)))
app.add_middleware(CSRFMiddleware(CSRFConfig()))
app.template_global("csrf_field")(csrf_field)

# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.route("/")
def index():
    """Show the contact form."""
    return Template("index.html")


@app.route("/contact", methods=["POST"])
async def contact(request: Request):
    """Handle contact form submission."""
    form = await request.form()
    name = form.get("name", "").strip()
    email = form.get("email", "").strip()
    message = form.get("message", "").strip()
    website = form.get("website", "").strip()

    if not name or not email or not message:
        return Template(
            "index.html",
            error="Please fill in name, email, and message.",
            name=name,
            email=email,
            message=message,
            website=website,
        )

    # Store in session for thank-you page (demo only — real app would send email)
    session = get_session()
    session["contact_name"] = name
    session["contact_website"] = website

    return Redirect("/thank-you")


@app.route("/thank-you")
def thank_you():
    """Show thank-you page after form submission."""
    session = get_session()
    name = session.get("contact_name", "there")
    website = session.get("contact_website", "")
    return Template("thank_you.html", name=name, website=website)


if __name__ == "__main__":
    app.run()
