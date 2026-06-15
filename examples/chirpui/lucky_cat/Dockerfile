# Lucky Cat — Railway / container deploy.
#
# Self-contained image for the flagship ChirpUI crypto-exchange demo.
#
# BLEEDING EDGE: the demo uses features that are on Chirp's `main` branch but not
# yet in a PyPI release — the signal() realtime primitive (#239) and the chirp-ui
# CSP ownership fix (#233). So it installs Chirp straight from GitHub `main`
# rather than from PyPI. Once a release ships these, switch the install line to
# the published spec: `uv pip install --system "bengal-chirp[ui]>=<version>"`.
#
# Build context is THIS directory:
#     docker build -t lucky-cat examples/chirpui/lucky_cat
#
# Chirp reads PORT / RAILWAY_* from the environment via AppConfig.from_env(),
# so app.run() binds 0.0.0.0:$PORT on Railway with no extra flags.
FROM python:3.14-slim

# git is required to pip-install Chirp from its GitHub source.
RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

# uv for fast installs.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# Bleeding-edge Chirp from main with ALL extras (the example needs sessions
# [itsdangerous] + forms [python-multipart] beyond ui), plus chirp-ui explicitly
# so the component library is present regardless of the [all] extra's contents.
RUN uv pip install --system \
    "bengal-chirp[all] @ git+https://github.com/lbliii/chirp.git@main" \
    "chirp-ui>=0.9.0"

# The example is a flat package of sibling modules + a pages/ tree + static/.
# Copy the whole example directory; app.py inserts its own dir on sys.path.
COPY . /app/

# Single in-memory process — see README "Configuration": workers=1 is required
# because the wallet, trade store, SimFeed, and signal bus are process-local.
# CHIRP_SECRET_KEY must be set as a Railway service variable for production.
EXPOSE 8000
CMD ["python", "app.py"]
