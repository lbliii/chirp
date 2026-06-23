# Lucky Cat — Railway / container deploy.
#
# FREE-THREADED: the free-threading proof panel (/ft/stream) is only honest on a
# GIL-disabled interpreter, so the image runs CPython 3.14t (free-threaded).
#   * `python:3.14t-slim` is NOT a published tag — we install the free-threaded
#     interpreter with uv on a standard slim base.
#   * Extras are CURATED ([ui,sessions,forms]); [all]'s argon2-cffi/asyncpg are
#     C-extensions that can silently re-enable the GIL on a 3.14t build. The
#     example imports none of them (forms parsing is urlencoded, not multipart).
#
# Chirp installs from GIT @ GIT_REF (default: main), NOT a PyPI wheel, so the
# framework tracks the demo's bleeding edge and the two NEVER drift. The example's
# templates and handlers advance with main and routinely use APIs newer than the
# last published wheel — e.g. session-scoped signals (`app.signal(..., audience=
# "session")`) or signal_attrs(). Pinning to a wheel forced a patch release on
# every demo change and 500s/crashes when we forgot (the wheel's App.signal()
# lacked `audience`).
#
# Cache-bust: the `ADD` of GitHub's commits API below invalidates the install
# layer whenever GIT_REF moves (the JSON carries the latest SHA), so a rebuild
# re-fetches the newest code instead of serving a stale cached layer. Override
# GIT_REF (service variable or `--build-arg`) to pin a branch/tag/SHA.
#
# Named GIT_REF, NOT CHIRP_REF: on Railway the cache-bust var must be a *service*
# variable to reach this build ARG, and Railway also mirrors service vars into
# the runtime container env. A `CHIRP_*` name there trips Chirp's reserved-
# namespace guard (`_warn_unknown_env_vars`) with a UserWarning on every boot, so
# keep this outside the framework's namespace.
#
# Build context is THIS directory:
#     docker build -t lucky-cat examples/chirpui/lucky_cat
#
# Chirp reads PORT / RAILWAY_* via AppConfig.from_env(), so app.py binds
# 0.0.0.0:$PORT on Railway with no extra flags.
FROM python:3.14-slim

# uv for fast installs + managed Python.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# PYTHON_GIL=0 is belt-and-suspenders: a clean pure-Python 3.14t build already
# runs GIL-off; this also overrides a silent re-enable if a future dep ships
# without the free-threading marker. UV_LINK_MODE=copy avoids Docker hardlink
# warnings. The venv goes first on PATH so `python` is the 3.14t interpreter.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHON_GIL=0 \
    UV_LINK_MODE=copy \
    PATH="/opt/venv/bin:$PATH"

WORKDIR /app

# git: uv shells out to it to install Chirp from the git ref below (slim has none).
RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

# A free-threaded 3.14t virtualenv on PATH (uv fetches the interpreter — the same
# 3.14t CI runs on, .github/workflows/ci.yml).
RUN uv venv --python 3.14t /opt/venv

# Chirp + chirp-ui, built from GIT_REF (bleeding edge); CURATED extras only.
# The ADD fetches the ref's latest commit metadata; its body changes when the ref
# advances, so BuildKit invalidates the install layer and uv re-fetches the code.
ARG GIT_REF=main
ADD "https://api.github.com/repos/lbliii/chirp/commits/${GIT_REF}" /tmp/chirp-commit.json
RUN uv pip install --python /opt/venv/bin/python \
    "bengal-chirp[ui,sessions,forms,passkeys] @ git+https://github.com/lbliii/chirp.git@${GIT_REF}" \
    "websockets>=14.0" "httpx>=0.27.0"

# The example is a flat package of sibling modules + a pages/ tree + static/.
# Copy the whole example directory; app.py inserts its own dir on sys.path.
COPY . /app/

# Single in-memory process — see README "Configuration": workers=1 is required
# because the wallet, trade store, SimFeed, and signal bus are process-local.
# CHIRP_SECRET_KEY must be set as a Railway service variable for production.
# `python` resolves to /opt/venv/bin/python (3.14t) via PATH.
EXPOSE 8000
CMD ["python", "app.py"]
