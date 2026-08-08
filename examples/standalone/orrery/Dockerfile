# Orrery — Railway / container deploy.
#
# Chirp installs from GIT @ GIT_REF (default: main), NOT a PyPI wheel, so the
# framework tracks the demo's bleeding edge. Named GIT_REF (not CHIRP_REF) so
# Railway service vars mirrored into the runtime env stay outside Chirp's
# reserved CHIRP_* namespace.
#
# Build context is THIS directory:
#     docker build -t orrery examples/standalone/orrery
#
# Chirp reads PORT / RAILWAY_* via AppConfig.from_env().
FROM python:3.14-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/opt/venv/bin:$PATH"

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

RUN uv venv --python 3.14 /opt/venv

# Chirp + skill/sessions extras from GIT_REF. Cache-bust when the ref moves.
ARG GIT_REF=main
ADD "https://api.github.com/repos/lbliii/chirp/commits/${GIT_REF}" /tmp/chirp-commit.json
RUN uv pip install --python /opt/venv/bin/python \
    "bengal-chirp[skill,sessions] @ git+https://github.com/lbliii/chirp.git@${GIT_REF}" \
    "itsdangerous>=2.2.0"

COPY . /app/

EXPOSE 8000
CMD ["python", "app.py"]
