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
# Chirp installs from PyPI. Pin EXACTLY (==), not a floor (>=): the example
# templates in this repo advance with main, but the framework here is the last
# published wheel. A floor lets the two drift — the demo's reactive lobby uses
# signal_attrs(), added after 0.8.0, so a 0.8.0 wheel 500s with UndefinedError.
# Pinning to the release that ships every global the templates use keeps the two
# in lockstep. Bump this pin in the SAME release that ships the templates.
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

# A free-threaded 3.14t virtualenv on PATH (uv fetches the interpreter — the same
# 3.14t CI runs on, .github/workflows/ci.yml).
RUN uv venv --python 3.14t /opt/venv

# Published Chirp + chirp-ui from PyPI; CURATED extras only.
RUN uv pip install --python /opt/venv/bin/python \
    "bengal-chirp[ui,sessions,forms]==0.8.1"

# The example is a flat package of sibling modules + a pages/ tree + static/.
# Copy the whole example directory; app.py inserts its own dir on sys.path.
COPY . /app/

# Single in-memory process — see README "Configuration": workers=1 is required
# because the wallet, trade store, SimFeed, and signal bus are process-local.
# CHIRP_SECRET_KEY must be set as a Railway service variable for production.
# `python` resolves to /opt/venv/bin/python (3.14t) via PATH.
EXPOSE 8000
CMD ["python", "app.py"]
