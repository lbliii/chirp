"""Minimal project scaffolding templates (--minimal)."""

MINIMAL_APP_PY = """\
import os

from chirp import App, AppConfig, Request, Template
from chirp.middleware.csrf import CSRFConfig, CSRFMiddleware
from chirp.middleware.security_headers import SecurityHeadersMiddleware
from chirp.middleware.sessions import SessionConfig, SessionMiddleware

_DEFAULT_SECRET = "change-me-before-deploying"
_secret = os.environ.get("CHIRP_SECRET_KEY", _DEFAULT_SECRET)

# Env-driven so the generated app can run in any environment:
#   CHIRP_ENV=production   selects the production security contract track.
#   CHIRP_DEBUG=1          enables dev tooling (defaults on outside production).
_env = os.environ.get("CHIRP_ENV", "development")
_debug = os.environ.get("CHIRP_DEBUG", "1" if _env != "production" else "0") not in (
    "0",
    "false",
    "False",
    "",
)

config = AppConfig.from_env(
    secret_key=_secret,
    env=_env,
    debug=_debug,
)
app = App(config=config)

if config.env != "development" and config.secret_key == _DEFAULT_SECRET:
    msg = (
        "Refusing to start in production with default secret key. "
        "Set CHIRP_SECRET_KEY to a strong random value."
    )
    raise RuntimeError(msg)

app.add_middleware(
    SessionMiddleware(
        SessionConfig(
            secret_key=config.secret_key,
            # secure defaults to "auto": Secure cookies in production/staging
            # (resolved from AppConfig.env at freeze), off in local dev.
            httponly=True,
            samesite="lax",
        )
    )
)
app.add_middleware(CSRFMiddleware(CSRFConfig()))
app.add_middleware(SecurityHeadersMiddleware())


@app.route("/")
async def index(request: Request) -> Template:
    return Template("index.html", greeting="Hello, world!")


if __name__ == "__main__":
    app.run()
"""

MINIMAL_INDEX_HTML = """\
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <title>{{ greeting }}</title>
</head>
<body>
    <h1>{{ greeting }}</h1>
</body>
</html>
"""
