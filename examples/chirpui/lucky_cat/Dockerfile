# Lucky Cat — Railway / container deploy.
#
# Self-contained image for the flagship ChirpUI crypto-exchange demo. It pulls
# Chirp + the chirp-ui extra from PyPI (NOT the repo checkout) so the image is
# reproducible outside the monorepo, then runs the example's own entrypoint.
#
# Build context is THIS directory:
#     docker build -t lucky-cat examples/chirpui/lucky_cat
#
# Chirp reads PORT / RAILWAY_* from the environment via AppConfig.from_env(),
# so app.run() binds 0.0.0.0:$PORT on Railway with no extra flags.
FROM python:3.14-slim

# uv for fast, locked installs.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# bengal-chirp[ui] pulls in chirp-ui (the app-shell + component library this
# example requires) plus the core deps. Pin to the published release line.
RUN uv pip install --system "bengal-chirp[ui]>=0.7.1"

# The example is a flat package of sibling modules + a pages/ tree + static/.
# Copy the whole example directory; app.py inserts its own dir on sys.path.
COPY . /app/

# Single in-memory process — see README "Configuration": workers=1 is required
# because the wallet, trade store, SimFeed, and signal bus are process-local.
# CHIRP_SECRET_KEY must be set as a Railway service variable for production.
EXPOSE 8000
CMD ["python", "app.py"]
