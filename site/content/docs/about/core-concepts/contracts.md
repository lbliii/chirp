---
title: Contracts
description: "The app.check() model: fail-loud-at-startup validation of your hypermedia wiring."
draft: false
weight: 50
lang: en
type: doc
tags: ["contracts", "app.check", "validation", "startup"]
keywords: ["contracts", "app.check", "validation", "startup", "categories", "severity"]
category: explanation
---

## What contracts are

A **contract** is a rule about how your hypermedia app is wired — a fragment
points at a block that exists, an `hx-target` selector resolves to a real id, an
OOB region matches a registered block, an app with mutating routes ships the
secure-by-default middleware. `app.check()` validates all of these against the
frozen app and reports anything broken.

The point is **fail loud at startup, not silent at runtime**. A typo in an
`hx-target` or a renamed template block is the kind of bug that ships green and
breaks a swap in production. A contract catches it before the server starts
serving requests.

You rarely call `app.check()` by hand. In debug mode it runs automatically when
you start the dev server, and `chirp check myapp:app` runs it in CI. This page
explains the model — what categories and severities mean, how severity changes
with the environment, and how to add your own checks. For the full list of every
category and its fix target, see the reference: [[docs/quality/contracts-debugging/categories|Contract Category Reference]].

## The happy path: it just runs

When `AppConfig(debug=True)`, freeze runs the full contract suite and prints a
report to stderr. An ERROR-severity issue exits before the server starts.

```python
from chirp import App, AppConfig, Template

app = App(AppConfig(debug=True, template_dir="templates"))

@app.route("/")
def index():
    return Template("page.html")

app.run()  # freeze runs app.check(); ERRORs exit before serving
```

If everything is wired correctly you see a one-line summary and the server
starts. If a fragment points at a missing block, you get an ERROR naming the
template and block, and the process exits with code 1.

:::{tip}
Debug auto-run is gated on `config.debug`. Production apps (`debug=False`) do
**not** pay the check cost on every boot — you gate that in CI with `chirp check`
instead. See [[docs/reference/cli|the CLI reference]].
:::

## Categories vs severities

Two independent axes describe every issue.

A **category** is *what kind* of rule fired — a stable string handle like
`fragment`, `routing`, `oob_registry`, or `security_stack`. Use the category as
the key for CI policy: you promote or demote a whole category, never an
individual message.

A **severity** is *how much it matters*: `ERROR`, `WARNING`, or `INFO`.

:::{list-table}
:header-rows: 1

* - Severity
  - Meaning
  - Effect
* - `ERROR`
  - The app is broken — a swap will silently fail or a security floor is unmet.
  - Fails `app.check()`; exits before serving in debug.
* - `WARNING`
  - Likely a mistake, but the app still runs.
  - Reported; fails only with `--warnings-as-errors`.
* - `INFO`
  - Informational — static analysis can't be sure (e.g. an orphan route reached only by dynamic navigation).
  - Reported; never fails the check.
:::

The category is the part you reach for when writing policy. The message is the
concrete fix target — a good message names the route, template, block, selector,
registration, or config field that needs to change.

## Severity is environment-aware

Some rules fire at different severities depending on `AppConfig(env=...)`, which
is one of `"development"`, `"staging"`, or `"production"`. A missing
secure-by-default stack is the canonical example: an app with mutating routes
that omits CSRF/Session middleware is an **ERROR in production**, a **WARNING in
staging**, and **silent in development** — so dev apps and shipped examples stay
clean while a real deployment is held to the floor.

This is why `chirp check --deploy` exists: it runs the env-aware rules with
production posture even when you're checking locally, so deploy-blocking
misconfigurations escalate to ERROR the way they would in prod. It does not
mutate your app — a genuinely deploy-ready app still passes.

```bash
# Local CI gate — fail on any error or drift
chirp check myapp:app --warnings-as-errors

# Deploy preflight — production posture, implies --warnings-as-errors
chirp check myapp:app --deploy
```

:::{note} See also

The secure-by-default stack and its env-aware severity matrix are documented in
[[docs/quality/deployment/auth-hardening|Auth & hardening]]. The full per-category
severity table lives in [[docs/quality/contracts-debugging/categories|the category reference]].
:::

## Custom checks

Third-party packages and apps extend `app.check()` with their own rules. A check
is any callable taking `(snapshot, result)`: read the frozen
`ContractCheckSnapshot`, append `ContractIssue`s to `result.issues`.

```python
from chirp import ContractIssue, Severity

def no_todos(snapshot, result):
    for name, source in snapshot.template_sources.items():
        if "TODO" in source:
            result.issues.append(
                ContractIssue(Severity.WARNING, "todo", f"TODO in {name}", template=name)
            )

app.register_contract_check(no_todos)
```

Register during setup, before freeze — registering after freeze raises
`RuntimeError`. Exceptions inside a check are isolated: they become ERROR issues,
and the other checks still run. Both plain functions and callable class instances
satisfy the `ContractCheck` protocol.

### Passing data to a check

```python
app.set_contract_check_data("components", ["card", "modal"])

def component_check(snapshot, result):
    components = snapshot.extras["components"]  # → ["card", "modal"]
```

### Overriding a category's severity

Promote or demote a whole category as a post-processing step after every check
runs. This is your CI policy lever — apply it to built-in or custom categories
alike.

```python
from chirp import Severity

app.override_contract_severity("dead", Severity.ERROR)     # dead-template INFO → ERROR
app.override_contract_severity("orphan", Severity.WARNING) # orphan-route INFO → WARNING
```

:::{warning}
Do not demote a fail-loud category — a missing required OOB region, a broken SSE
listener — to silence a CI failure. The check is reporting a swap that will wipe
live DOM or a stream that will never fire. Fix the wiring, not the severity.
:::

:::{dropdown} Opting out of the debug auto-run
The contract suite runs on `app.run()` / `app.freeze()` only when
`config.debug=True`. To skip it entirely (for example, a fast test harness that
freezes many throwaway apps):

```python
app = App(AppConfig(debug=True, skip_contract_checks=True))
```

Or set the environment variable `CHIRP_SKIP_CONTRACT_CHECKS=1`. Prefer fixing the
contract over skipping the check — the suite is what makes a typo'd swap a startup
error instead of a production incident.
:::{/dropdown}

## Next steps

- [[docs/quality/contracts-debugging/categories|Contract Category Reference]] — every category, its default severity, and its fix target.
- [[docs/reference/cli|CLI reference]] — `chirp check`, `--deploy`, `--warnings-as-errors`.
- [[docs/about/core-concepts/app-lifecycle|App Lifecycle]] — when freeze runs and why the app becomes immutable.

:::{related}
:::
