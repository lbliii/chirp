---
title: CLI
description: "Command reference for the chirp CLI: chirp new (scaffold), chirp check (validate contracts), and chirp shapes-codegen."
draft: false
weight: 30
lang: en
type: doc
tags: ["cli", "chirp new", "chirp check", "shapes-codegen"]
keywords: ["cli", "chirp new", "chirp check", "shapes-codegen", "command", "scaffold", "deploy", "warnings-as-errors"]
category: reference
---

## Overview

`chirp` is the command-line entry point installed with the framework. You use it
to scaffold a new project, validate your hypermedia wiring, run the dev or
production server, and inspect routes. This page is the reference for the three
commands you reach for most — `chirp new`, `chirp check`, and
`chirp shapes-codegen` — plus a table of the rest.

Commands that operate on an application take an **import string** of the form
`module:attribute` (for example `myapp:app`). When you omit the attribute, it
defaults to `app`, so `myapp` resolves to `myapp.app`. A callable that is not
already an `App` — an app factory like `create_app` — is called to produce one.
Scaffolding and migration commands instead take filesystem/database arguments;
`shapes-codegen` treats its path as an app import only with `--audit`.

The command tree is registered through Milo 0.4.x. Existing Chirp command
names, positionals, flags, defaults, output channels, and exit codes remain the
compatibility contract. Help uses Milo's typed presentation and adds framework
root operations. `check`, `diff`, and `routes` are the explicit read-only MCP
and llms.txt allowlist; every lifecycle or write-capable command remains
CLI-only. The selected inspections also support Milo's `--format json` and
`--output-file` controls while preserving their existing terminal output.

```bash
chirp --version        # chirp, kida, pounce, and Python versions
chirp <command> --help # flags for any command
```

The migration-grade inventory of every command, flag, default, output channel,
exit code, lazy-import boundary, agent-exposure decision, and Milo mapping is
maintained in [`docs/cli-compatibility-contract.md`](https://github.com/lbliii/chirp/blob/main/docs/cli-compatibility-contract.md).

## Command summary

:::{list-table}
:header-rows: 1

* - Command
  - What it does
* - `chirp new <name>`
  - Scaffold a new project directory.
* - `chirp check <app>`
  - Validate hypermedia contracts (mirrors `app.check()`).
* - `chirp diff <app> --base <ref>`
  - Diff hypermedia contracts against a git baseline; supports stable JSON output.
* - `chirp shapes-codegen [path]`
  - Suggest `@shape` decorators and audit Shape drift.
* - `chirp run <app>`
  - Start the dev or production server.
* - `chirp dev <app>`
  - Dev server with browser reload on template/CSS changes.
* - `chirp routes <app>`
  - Print the registered route table, including normalized QUERY media ranges.
* - `chirp security-check <app>`
  - Audit config against an OWASP checklist.
* - `chirp freeze <app> <out>`
  - Render routes to static HTML files.
* - `chirp makemigrations`
  - Generate a schema migration from a SQL diff.
* - `chirp migrate`
  - Apply pending schema migrations (one-shot deploy job).
:::

The three commands below are documented in full. For `run`/`dev` see
[[docs/quality/deployment/production|Production deployment]]; for `freeze` see
[[docs/quality/deployment/freeze-hybrid|Freeze and hybrid hosting]]; for
`makemigrations` and `migrate` see [[docs/build-apps/forms-data/database|Database]].

## Agent inspection

Use `chirp --llms-txt` to inspect the agent-readable command contract or
`chirp --mcp` to serve the reviewed tools to an MCP host. The allowlist is:

- `check` — structured contract issues and optional coverage;
- `diff` — the existing stable git-baseline diff payload;
- `routes` — method, path, handler, and route-name records.

These tools are read-only but open-world: importing `myapp:app` executes trusted
project Python code, and `diff` reads git history through a temporary detached
worktree. Scaffold, server, freeze, migration, security-check, and codegen
commands are not discoverable or callable through MCP.

---

## `chirp new` — scaffold a project

`chirp new <name>` creates a project directory you can run immediately. The
default scaffold is auth-ready: a filesystem-routed `pages/` tree with a login
flow, a dashboard, explicit app-owned Kida components and patterns, the
secure-by-default middleware stack, and a passing `chirp check`. Flags switch to
a different starting point.

```bash
chirp new myapp
cd myapp && python app.py
```

The default scaffold prints its own next steps — a login of `admin` / `password`
and a dashboard at `/dashboard`. It refuses to overwrite an existing directory.

:::{list-table}
:header-rows: 1

* - Flag
  - Result
* - *(none)*
  - Auth + dashboard + filesystem routing (`pages/`), app-owned components and patterns (`templates/`), layered `static/css` tokens/theme, tests, `pyproject.toml`.
* - `--minimal`
  - A single-file project: `app.py` plus `templates/index.html`.
* - `--sse`
  - SSE boilerplate — an `EventStream` route wired with `sse_scope`.
* - `--shell`
  - A persistent [[docs/build-apps/ui-extensions/app-shell|app shell]] (topbar, sidebar) over filesystem routing.
* - `--stream`
  - Simulated token streaming with `TemplateStream` plus an `EventStream` activity panel.
* - `--ai`
  - AI chat with tools, an SSE activity feed, and the secure stack.
* - `--skill`
  - Signed skill app (`skill.tool` + `use_skill`), secure stack, and Railway config.
* - `--with-chirpui`
  - Require [[docs/build-apps/ui-extensions/chirp-ui|chirp-ui]] templates; fail if it is not installed.
:::

Every scaffold — including `--minimal` — wires the secure-by-default stack
(`SessionMiddleware` → `CSRFMiddleware` → `SecurityHeadersMiddleware`) and reads
the secret key from `CHIRP_SECRET_KEY`, so a generated app passes `chirp check`
out of the box.

:::{note}
Default generation is deterministic: merely installing chirp-ui never changes
the files `chirp new` writes. `--with-chirpui` is the explicit compatibility
choice and a hard requirement, not a hint; it exits with an error when chirp-ui
is missing, so CI cannot silently produce a different scaffold.
:::

## `chirp check` — validate contracts

`chirp check <app>` resolves the app, runs the contract suite, and prints the
report. It is the same validation that [[docs/about/core-concepts/contracts|`app.check()`]]
runs in debug mode — fail loud at startup, not silent at runtime. The process
exits with code 1 when any ERROR-severity issue is found, which makes it a CI
gate.

```bash
chirp check myapp:app
```

:::{list-table}
:header-rows: 1

* - Flag
  - Effect
* - `--warnings-as-errors`
  - Exit 1 if any WARNING is present, not just ERRORs. The standard CI posture.
* - `--coverage`
  - Print route/template contract coverage counters alongside the report.
* - `--deploy`
  - Run env-aware rules with production-posture severity. Implies `--warnings-as-errors`.
* - `--json`
  - Emit the stable machine-readable contract report.
* - `--baseline PATH`
  - Compare against a JSON report from an earlier `--json` run.
* - `--include-info`
  - Include INFO findings in structured JSON/baseline modes.
:::

`--deploy` is the deploy preflight. Some rules — a missing secure-by-default
stack on an app with mutating routes is the canonical one — fire at a lower
severity in development than in production. `--deploy` escalates those to
production posture even when you run it locally, so a deploy-blocking
misconfiguration surfaces as an ERROR before you ship. It does not mutate your
app; a genuinely deploy-ready app still passes.

```bash
# Standard CI gate — fail on any error or warning
chirp check myapp:app --warnings-as-errors

# Deploy preflight — production posture (implies --warnings-as-errors)
chirp check myapp:app --deploy
```

:::{note} See also

The model behind this command — categories versus severities, environment-aware
severity, and custom checks — lives in
[[docs/about/core-concepts/contracts|Contracts]]. The full per-category severity
table is the [[docs/quality/contracts-debugging/categories|Contract Category Reference]].
:::

## `chirp shapes-codegen` — adopt and audit Shapes

:::{since} 0.8
:::

`chirp shapes-codegen [path]` helps you adopt [[docs/build-apps/forms-data/shapes|Shapes]]
incrementally. It has two non-destructive modes.

**Suggest decorators (default).** It scans Python files for frozen dataclasses
sitting near an explicit named-column `SELECT` literal, pairs each class to the
`SELECT` whose output columns are a subset of its fields, and prints a
`@shape(...)` suggestion above each match. `--dry-run` is the default and the
only write behavior — nothing on disk changes.

```bash
chirp shapes-codegen pages/
```

```text
--- pages/boards.py:14 (BoardView)
+ @shape('SELECT id, title FROM boards WHERE id = :id')
  @dataclass(frozen=True, slots=True)
  class BoardView:  # columns: id, title
3 @shape suggestion(s) (dry-run — no files written).
```

Already-decorated classes are skipped, and only `SELECT`s the conservative parser
can read are paired (`SELECT *`, expressions, CTEs, and `UNION` are skipped), so a
suggestion is always one the contract checker can later verify.

**Audit drift (`--audit`).** It loads an app and reports every surface-contract
name with no backing Shape, reusing the exact registry-drift logic `app.check()`
runs. With `--audit`, `path` becomes an app import string, and the command exits
non-zero when drift is found — so it drops straight into CI.

```bash
chirp shapes-codegen myapp:app --audit
```

:::{list-table}
:header-rows: 1

* - Argument / flag
  - Purpose
* - `path`
  - Directory or file to scan (default `.`); with `--audit`, an app import string like `myapp:app`.
* - `--dry-run`
  - Print suggested `@shape` decorators without writing files (the default behavior).
* - `--audit`
  - Audit `surface_contracts` for names with no backing Shape; exit non-zero on drift.
* - `--migrations DIR`
  - Migrations directory (reserved for future incremental codegen output).
:::

## `chirp migrate` — apply pending migrations

:::{since} 0.9
:::

`chirp migrate --db <url> --migrations-dir <dir>` applies pending migrations
from a directory as a **one-shot job**. It connects to the database, runs
[[docs/build-apps/forms-data/database|`migrate()`]], prints a summary, and
disconnects. It does **not** import or boot your app (no freeze, no contract
checks) — it takes the same `--db` / `--migrations-dir` flags as
`makemigrations`, not an app import string.

```bash
chirp migrate --db "$DATABASE_URL" --migrations-dir migrations
```

It is fail-loud: a failed migration, an invalid migrations directory, or a
checksum-drift edit of an already-applied migration prints the error and exits
`1`. Nothing is swallowed.

Pair it with `AppConfig(skip_migrations=True)` (or `CHIRP_SKIP_MIGRATIONS=1`) so
the app does not also run migrations on boot. In a multi-replica deploy this
lets a single pre-deploy job own migration application instead of every replica
racing on startup. When the on-boot run is skipped, the app logs a
`lifecycle:migrations-skipped` warning so a missing deploy job (and the
resulting stale schema) is visible. See
[[docs/quality/deployment/production|Production deployment]].

:::{list-table}
:header-rows: 1

* - Flag
  - Effect
* - `--db`
  - Database URL (required), e.g. `sqlite:///app.db`.
* - `--migrations-dir`
  - Directory containing migration files (default `migrations`).
:::

## Gotchas

:::{warning}
`chirp check` and the other app-loading commands **import your app module** to
resolve the import string. Side effects at import time — opening a database,
binding a port — run during the check. Keep module-level code import-safe, and
put startup work behind `app.run()` or a factory function.
:::

## See also

:::{note} See also

- [[docs/about/core-concepts/contracts|Contracts]] — the `app.check()` model `chirp check` runs.
- [[docs/quality/contracts-debugging/categories|Contract Category Reference]] — every category and its default severity.
- [[docs/build-apps/forms-data/shapes|Shapes]] — the full `shapes-codegen` migration story.
- [[docs/get-started/quickstart|Quickstart]] — scaffold a project and run it.
:::

:::{related}
:::
