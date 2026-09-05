"""Minimal project scaffolding templates (--minimal)."""

MINIMAL_APP_PY = """\
import os

from project_paths import ROOT

from chirp import secure_stack

from chirp import App, AppConfig, Request, Template

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
    csp_nonce_enabled=True,
    secret_key=_secret,
    template_dir=ROOT / "templates",
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

for middleware in secure_stack(config):
    app.add_middleware(middleware)


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
