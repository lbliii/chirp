---
title: Learning Path
description: Numbered curriculum from install to deployment — the recommended first-week path through Chirp docs and examples
draft: false
weight: 5
lang: en
type: doc
tags: [getting-started, learning-path, curriculum]
keywords: [learning path, curriculum, onboarding, tutorial order]
category: onboarding
---

Follow these steps in order. Each link is self-contained; later steps assume earlier ones.

## 1. Install and verify

[[docs/get-started/installation|Installation]] — `pip install bengal-chirp` or `uv add bengal-chirp`, Python 3.14+.

For new projects, add the UI extra so `chirp new` scaffolds ChirpUI layouts:

```bash
pip install 'bengal-chirp[ui]'
```

## 2. Run your first app

Pick one entry point:

- **Scaffold (recommended):** [[docs/get-started/quickstart|Quickstart]] — `chirp new myapp && python app.py`
- **Smallest loop:** [[docs/get-started/first-fragment-app|First Fragment App]] — one file, one template, `Page` / `Fragment`, tests

Both teach the hypermedia loop: full page for browsers, HTML fragment for htmx.

## 3. Learn the mental model

[[docs/about/core-concepts/return-values|Return values]] — the type *is* the intent (`Template`, `Page`, `Fragment`, `FormAction`, …).

Skim [[docs/about/core-concepts/hypermedia-model|Hypermedia model]] if you want the why before building more.

## 4. Learn project shape

[[docs/get-started/project-layout|Project layout]] — where `chirp new` puts handlers, templates, static files, and tests.

## 5. Tier 1 — basics (examples)

Run and read the standalone examples:

| Example | Teaches |
|---------|---------|
| [[docs/examples/contacts|Contacts]] | Forms, validation, `Page` / `Fragment`, OOB |
| [[docs/examples/returns-gallery|Returns gallery]] | Every return type on one page |
| [[docs/examples/sse|SSE]] | Minimal post-load updates |

Recipe collection: [[docs/tutorials/htmx-patterns|htmx Patterns]].

## 6. Validate wiring

[[docs/about/core-concepts/contracts|Contracts]] — what `chirp check` validates and why.

Run on your app:

```bash
chirp check myapp:app
chirp check myapp:app --warnings-as-errors   # CI posture
```

Category reference: [[docs/quality/contracts-debugging/categories|Contract categories]].

## 7. Tier 2 — app shell (optional)

When you want ChirpUI layouts and boosted navigation:

[[docs/examples/contacts-shell|Contacts shell]] — `_actions.py`, `_context.py`, shell swaps.

## 8. Tier 3 — capstone

[[docs/examples/lucky-cat|Lucky Cat]] — signals, Suspense, SSE, OOB, auth, secure stack.

**Live demo:** [luckycat-production.up.railway.app](https://luckycat-production.up.railway.app) ·
**Source:** `examples/chirpui/lucky_cat/`

Complete tiers 1–2 first. Lucky Cat is the composed product demo, not the on-ramp.

Follow the [[docs/tutorials/full-application-journey|full-application journey]]
when you want one tested path from SQLite and dual-mode forms through boosted
shell navigation, Suspense, SSE, contract diagnostics, and deployment posture.

## 9. Ship

When you deploy:

[[docs/quality/deployment/production|Production deployment]] — Pounce, `chirp check --deploy`, workers, metrics.

---

## Where to go after this path

| I want to… | Go to… |
|------------|--------|
| Implement a feature | [[docs/build-apps/_index|Build Apps]] |
| Migrate from Flask | [[docs/tutorials/coming-from-flask|Coming from Flask]] |
| Add auth | [[docs/tutorials/auth-login-walkthrough|Login walkthrough]] |
| Look up a symbol | [[docs/reference/_index|Reference]] · [[docs/reference/glossary|Glossary]] |

:::{related}
:limit: 3
:section_title: Next Steps
:::
