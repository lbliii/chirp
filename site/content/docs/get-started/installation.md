---
title: Installation
description: Install Chirp and optional extras
draft: false
weight: 10
lang: en
type: doc
tags: [installation, setup]
keywords: [install, pip, uv, extras, forms, sessions, auth, testing]
category: onboarding
---

Get Chirp installed, add the optional extras your app needs, and scaffold a
running project. Chirp is a small core — the [[docs/build-apps/html-fragments/kida-integration|Kida template engine]]
plus an async runtime — and every other capability (forms, sessions, auth, a
database, UI components) is an opt-in extra you add when you reach for it.

## Prerequisites

- **Python 3.14+** (free-threading build recommended)

:::{note}
Chirp runs on both the GIL and [[docs/about/thread-safety|free-threading]]
builds of Python 3.14. The free-threading build unlocks true parallelism for
concurrent request handling.
:::

## Install

::::{code-tabs}
:sync: install

```bash
# uv
uv add bengal-chirp
```

```bash
# pip
pip install bengal-chirp
```

```bash
# From source
git clone https://github.com/lbliii/chirp.git
cd chirp
uv sync --group dev
```

::::

## Verify

```python
import chirp
print(chirp.__version__)
```

You should see the installed version printed. Now [[docs/get-started/quickstart|scaffold your first project]]:

```bash
chirp new myapp
cd myapp
python app.py
```

Open `http://127.0.0.1:8000` in your browser.

## Optional extras

The core install pulls in just the template engine and async runtime. Everything
else is an opt-in extra. Most apps reach for a handful first:

| Extra | Provides | Install |
|-------|----------|---------|
| `forms` | [[docs/build-apps/forms-data/forms-validation|Multipart form parsing]] (file uploads) | `uv add "bengal-chirp[forms]"` |
| `sessions` | Signed cookie sessions ([[docs/quality/deployment/auth-hardening|hardening guide]]) | `uv add "bengal-chirp[sessions]"` |
| `auth` | Argon2 password hashing | `uv add "bengal-chirp[auth]"` |
| `testing` | The [[docs/quality/testing/test-client|test client]] (httpx transport) | `uv add "bengal-chirp[testing]"` |

```bash
# Common starting set for a full-stack app
uv add "bengal-chirp[forms,sessions,testing]"
```

:::{dropdown} All optional extras
| Extra | Provides | Pulls in |
|-------|----------|----------|
| `forms` | Multipart form parsing (file uploads) | `python-multipart` |
| `sessions` | Signed cookie sessions | `itsdangerous` |
| `auth` | Argon2 password hashing | `argon2-cffi` |
| `testing` | Test client transport | `httpx` |
| `data-pg` | [[docs/build-apps/forms-data/database|PostgreSQL access]] | `asyncpg` |
| `ai` | LLM streaming over raw HTTP | `httpx` |
| `markdown` | Markdown rendering with syntax highlighting | `patitas[syntax]` |
| `ui` | [[docs/build-apps/ui-extensions/chirp-ui|chirp-ui component library]] | `chirp-ui` |
| `config` | Load config from a local `.env` file | `python-dotenv` |
| `redis` | Redis-backed sessions and rate limiting | `redis` |
| `all` | The common extras together | `forms` + `sessions` + `auth` + `testing`/`ai` + `data-pg` + `markdown` |

SQLite needs no extra — it ships in the standard library as `sqlite3`. The `all`
extra covers the broadly useful set; it does **not** include `ui`, `config`, or
`redis`, which you add deliberately. Install several at once with a comma list:
`uv add "bengal-chirp[forms,auth,data-pg]"`.
:::

:::{dropdown} Working on Chirp itself?
Clone the repository and let `uv` resolve the development dependencies the same
way CI does:

```bash
git clone https://github.com/lbliii/chirp.git
cd chirp
uv sync --group dev
uv run pytest -q --tb=short
```
:::

## CLI commands

After installation the `chirp` command is available:

| Command | Description |
|---------|-------------|
| `chirp new <name>` | Scaffold an auth-ready project with filesystem pages, static assets, and tests |
| `chirp new <name> --minimal` | Scaffold a minimal single-file project |
| `chirp new <name> --shell` | Scaffold with a persistent app shell (topbar + sidebar) |
| `chirp new <name> --sse` | Scaffold with SSE boilerplate (`EventStream`, `sse_scope`) |
| `chirp new <name> --with-chirpui` | Require ChirpUI templates (fail if `chirp-ui` is not installed) |
| `chirp dev <app>` | Development server with browser reload on template/CSS changes |
| `chirp run <app>` | Start the server (e.g. `chirp run myapp:app`) |
| `chirp check <app>` | [[docs/quality/contracts-debugging/categories|Validate hypermedia contracts]] from the command line |
| `chirp check <app> --warnings-as-errors` | Exit non-zero on contract warnings (CI gate) |
| `chirp check <app> --coverage` | Show route/template contract coverage counters |
| `chirp check <app> --deploy` | Run checks at production severity (implies `--warnings-as-errors`) |
| `chirp routes <app>` | Print the registered route table |
| `chirp freeze <app> <output>` | Render routes to static HTML files |
| `chirp security-check <app>` | Audit app config against the security checklist |
| `chirp makemigrations --db <url> --schema <module>` | Generate a schema migration from model changes |
| `chirp migrate --db <url> --migrations-dir <dir>` | Apply pending schema migrations (one-shot deploy job) |

See the [[docs/reference/cli|CLI reference]] for full flag details.

## Next steps

:::{related}
:limit: 3
:section_title: Next Steps
:::
