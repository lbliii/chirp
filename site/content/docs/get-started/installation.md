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

## Prerequisites

- **Python 3.14+** (free-threading build recommended)

:::{note}
Chirp works on both GIL and free-threading builds of Python 3.14. Free-threading unlocks true parallelism for concurrent request handling.
:::

## Install

:::{tab-set}
:::{tab-item} uv
```bash
uv add bengal-chirp
```
:::{/tab-item}

:::{tab-item} pip
```bash
pip install bengal-chirp
```
:::{/tab-item}

:::{tab-item} From Source
```bash
git clone https://github.com/lbliii/chirp.git
cd chirp
uv sync --group dev
```
:::{/tab-item}
:::{/tab-set}

## Optional Extras

Chirp ships with two core dependencies: `kida` (template engine) and `anyio` (async runtime). Everything else is an optional extra:

| Extra | Provides | Install |
|-------|----------|---------|
| `forms` | Multipart form parsing | `pip install bengal-chirp[forms]` |
| `sessions` | Signed cookie sessions via itsdangerous | `pip install bengal-chirp[sessions]` |
| `auth` | Password hashing via argon2 | `pip install bengal-chirp[auth]` |
| `testing` | Test client via httpx | `pip install bengal-chirp[testing]` |
| `data` | SQLite access via aiosqlite | `pip install bengal-chirp[data]` |
| `data-pg` | PostgreSQL access via asyncpg | `pip install bengal-chirp[data-pg]` |
| `ai` | LLM streaming via httpx | `pip install bengal-chirp[ai]` |
| `all` | Everything above | `pip install bengal-chirp[all]` |

```bash
# Install with common extras for a full-stack app
uv add "bengal-chirp[forms,sessions,testing]"
```

## Verify

```python
import chirp
print(chirp.__version__)
```

Chirp has no CLI entry point -- it is a library. You create an `App` and call `app.run()` to start the development server.

## Next Steps

- [[docs/get-started/quickstart|Quickstart]] -- Build your first app
- [[docs/core-concepts/configuration|Configuration]] -- All AppConfig options
