"""Orrery — Railway dogfood host for N wrapped skills (#985 / epic #964).

Mounts ``gaze`` / ``resolve`` / ``star`` via ``mount_skills`` onto one aggregated
``/mcp``, exposes discovery at ``/skills``, and a hypermedia console at
``/console``. A home-page live feed bridges ``ToolEventBus`` → ``EventStream``
so agent invocations appear without waiting on sibling #983's framework hook.

Run locally::

    PYTHONPATH=src uv run --extra skill --extra sessions \\
        python examples/standalone/orrery/app.py

Point an MCP client at ``/mcp``. Open ``/`` for the live feed or ``/console``
to browse manifests and reliability scores.
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

from dogfood import DOGFOOD_CORPUS, N_DOGFOOD_SKILLS, build_dogfood_skills

from chirp import App, AppConfig, EventStream, Fragment, Request, Template, secure_stack
from chirp.middleware.csrf import CSRFConfig
from chirp.middleware.security_headers import SecurityHeadersConfig
from chirp.skill import (
    ReliabilityStore,
    mount_console,
    mount_skills,
)
from chirp.skill.smoke import render_faithful_answer, run_smoke

TEMPLATES_DIR = Path(__file__).parent / "templates"

# Default secure_stack CSP allows CDN scripts but NOT inline <style>, style=, or
# fonts.googleapis.com — which blanked the branded home page in production.
# Keep scripts host-allowlisted; permit the demo's inline CSS + Google Fonts.
_ORRERY_CSP = (
    "default-src 'self'; "
    "img-src 'self' data:; "
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
    "font-src 'self' https://fonts.gstatic.com data:; "
    "script-src 'self' 'unsafe-inline' https://unpkg.com https://cdn.jsdelivr.net; "
    "connect-src 'self'; "
    "base-uri 'self'; frame-ancestors 'none'; object-src 'none'"
)

_DEFAULT_SECRET = "change-me-before-deploying"
_secret = os.environ.get("CHIRP_SECRET_KEY", _DEFAULT_SECRET)
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
    template_dir=TEMPLATES_DIR,
    worker_mode="async",
)
app = App(config=config)

if config.env != "development" and config.secret_key == _DEFAULT_SECRET:
    msg = (
        "Refusing to start in production with default secret key. "
        "Set CHIRP_SECRET_KEY to a strong random value."
    )
    raise RuntimeError(msg)

for middleware in secure_stack(
    app.config,
    # MCP JSON-RPC clients have no browser CSRF cookie; exempt the machine face.
    csrf=CSRFConfig(exempt_paths=frozenset({"/mcp"})),
    headers=SecurityHeadersConfig(content_security_policy=_ORRERY_CSP),
):
    app.add_middleware(middleware)


# ---------------------------------------------------------------------------
# Dogfood skills → aggregated /mcp + discovery + console
# ---------------------------------------------------------------------------

_skills = build_dogfood_skills()
registry = mount_skills(app, _skills)
scores = ReliabilityStore()
mount_console(app, registry, scores=scores)


@app.template_filter("format_args")
def format_args(args: dict) -> str:
    """Format tool-call arguments for the live activity feed."""
    if not args:
        return "—"
    parts = []
    for key, value in args.items():
        parts.append(f'{key}="{value}"' if isinstance(value, str) else f"{key}={value}")
    return ", ".join(parts)


@app.template_filter("format_call_time")
def format_call_time(timestamp: float) -> str:
    """Format a unix timestamp for the live activity feed."""
    from datetime import UTC, datetime

    return datetime.fromtimestamp(timestamp, tz=UTC).strftime("%H:%M:%S")


@app.route("/")
def index(request: Request) -> Template:
    """Host landing — brand + paths + live invocation feed."""
    return Template(
        "index.html",
        skill_count=N_DOGFOOD_SKILLS,
        skill_names=tuple(s.name for s in registry.skills()),
        console_path="/console",
        discovery_path=registry.discovery_path or "/skills",
        mcp_path=app.config.mcp_path,
    )


@app.route("/feed", referenced=True)
def feed():
    """Stream tool-call events so agent invocations appear on the home console."""

    async def generate():
        async for event in app.tool_events.subscribe():
            yield Fragment("index.html", "activity_row", event=event)

    return EventStream(generate())


# Publish-oracle dogfood: freeze + smoke after all routes are registered so the
# console shows ReliabilityScore values. Skip with ORRERY_SKIP_PUBLISH=1.
# Also skip ``run_smoke`` when an event loop is already running (async pytest
# loaders) — ``asyncio.run`` inside ``run_smoke`` cannot nest.
if os.environ.get("ORRERY_SKIP_PUBLISH", "").strip() not in ("1", "true", "True"):
    app.freeze()
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        _smoke = run_smoke(app, DOGFOOD_CORPUS, answer_fn=render_faithful_answer)
        for _skill in registry.skills():
            scores.record(_skill.name, _smoke)


if __name__ == "__main__":
    app.run()
