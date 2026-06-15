# Lucky Cat — Railway / container deploy.
#
# FREE-THREADED + BLEEDING EDGE: the free-threading proof panel (/ft/stream) is
# only honest on a GIL-disabled interpreter, so the image runs CPython 3.14t
# (free-threaded). It installs Chirp from GitHub `main` because the demo needs
# signal() (#239) + the chirp-ui CSP fix (#233), not yet on PyPI.
#   * `python:3.14t-slim` is NOT a published tag — we install the free-threaded
#     interpreter with uv on a standard slim base.
#   * Extras are CURATED ([ui,sessions,forms]); [all]'s argon2-cffi/asyncpg are
#     C-extensions that can silently re-enable the GIL on a 3.14t build. The
#     example imports none of them (forms parsing is urlencoded, not multipart).
#
# Build context is THIS directory:
#     docker build -t lucky-cat examples/chirpui/lucky_cat
#
# Chirp reads PORT / RAILWAY_* via AppConfig.from_env(), so app.py binds
# 0.0.0.0:$PORT on Railway with no extra flags.
FROM python:3.14-slim

# git: pip-install Chirp from source. (uv downloads the 3.14t interpreter itself.)
RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

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

# Bleeding-edge Chirp from main + chirp-ui, CURATED extras only. CHIRP_REF busts
# Docker's layer cache (git+...@main is cached by instruction text); the deploy
# sets it to the commit SHA (Railway injects the service var as the build ARG),
# so each deploy invalidates this layer and re-pulls Chirp at that exact commit.
ARG CHIRP_REF=main
RUN uv pip install --python /opt/venv/bin/python \
    "bengal-chirp[ui,sessions,forms] @ git+https://github.com/lbliii/chirp.git@${CHIRP_REF}" \
    "chirp-ui>=0.9.0"

# The example is a flat package of sibling modules + a pages/ tree + static/.
# Copy the whole example directory; app.py inserts its own dir on sys.path.
COPY . /app/

# Single in-memory process — see README "Configuration": workers=1 is required
# because the wallet, trade store, SimFeed, and signal bus are process-local.
# CHIRP_SECRET_KEY must be set as a Railway service variable for production.
# `python` resolves to /opt/venv/bin/python (3.14t) via PATH.
EXPOSE 8000
CMD ["python", "app.py"]
