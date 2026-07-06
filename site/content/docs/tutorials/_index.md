---
title: Applied Tutorials
description: Step-by-step walkthroughs that apply Chirp patterns in context
draft: false
weight: 110
lang: en
type: doc
tags: [tutorials, guides, patterns]
keywords: [tutorials, python web framework, flask migration, htmx, patterns, server-rendered]
category: tutorial
icon: graduation-cap

cascade:
  type: doc
---

Tutorials are guided, end-to-end builds — pick one and follow it through. They
are for a developer mapping prior framework knowledge onto Chirp, or one who has
the basics and wants to ship a real feature.

Complete [[docs/get-started/learning-path|the learning path]] first unless the
table below points you here directly.

## When to use which tutorial

| Tutorial | Use when |
|----------|----------|
| [Coming from Flask](/chirp/docs/tutorials/coming-from-flask/) | You know Flask and want a concept map to Chirp |
| [Login walkthrough](/chirp/docs/tutorials/auth-login-walkthrough/) | You need auth, sessions, and `app.check()` on a login loop |
| [htmx Patterns](/chirp/docs/tutorials/htmx-patterns/) | You want copy-paste recipes after tier 1 examples |
| [Alpine + htmx](/chirp/docs/tutorials/alpine-htmx/) | You combine chirp-ui / Alpine with htmx |
| [View Transitions + OOB](/chirp/docs/tutorials/view-transitions-oob/) | You animate multi-target swaps |
| [Lucky Cat trade panel](/chirp/docs/tutorials/lucky-cat-trade-panel/) | You finished tier 2 and want one capstone feature dissected |
| [Full-application journey](/chirp/docs/tutorials/full-application-journey/) | You want the tested path from SQLite through forms, shell swaps, Suspense, SSE, checks, and deployment |
| [Passkeys walkthrough](/chirp/docs/tutorials/passkeys-walkthrough/) | You add WebAuthn on top of the secure stack |

:::{child-cards}
:::
