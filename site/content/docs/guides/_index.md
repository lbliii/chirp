---
title: Guides
description: Best practices and patterns for building accessible, secure, server-rendered Chirp applications
draft: false
weight: 105
lang: en
type: doc
tags: [guides, best-practices, accessibility]
keywords: [guides, htmx, server-rendered, accessibility, best-practices]
category: guide
icon: book

cascade:
  type: doc
---

:::{cards}
:columns: 2
:gap: medium

:::{card} Accessibility
:icon: user
:link: /chirp/docs/guides/accessibility/
:description: Semantic markup, ARIA, and WCAG alignment
Build inclusive apps with Chirp.
:::{/card}

:::{card} Alpine.js
:icon: layers
:link: /chirp/docs/guides/alpine/
:description: Local UI state — dropdowns, modals, tabs
Complement htmx with Alpine for client-only interactivity.
:::{/card}

:::{card} Shells
:icon: sidebar
:link: /chirp/docs/guides/shells/
:description: The three root layouts — boost, shell, app-shell
Pick exactly one per app. Includes the decision table, the `hx-select` distinction, and what is *not* a shell.
:::{/card}

:::{card} App Shells
:icon: sidebar
:link: /chirp/docs/guides/app-shell/
:description: chirp-ui's app_shell_layout — sidebar, topbar, OOB regions
The opinionated shell with persistent chrome. One of three shells; see [Shells](/chirp/docs/guides/shells/) for the others.
:::{/card}

:::{card} Boosted Navigation
:icon: arrow-right
:link: /chirp/docs/guides/boosted-navigation/
:description: hx-boost contract, cross-shell redirects, debug warnings
How swaps work, when they redirect, and the tripwires that catch silent failures.
:::{/card}

:::{card} UI layers & shell regions
:icon: layers
:link: /chirp/docs/guides/ui-layers/
:description: Glossary — app shell, page chrome, surface chrome, OOB ids
One vocabulary for Chirp + chirp-ui layouts and ``chirp.shell_regions``.
:::{/card}

:::{card} chirp-ui
:icon: palette
:link: /chirp/docs/guides/chirp-ui/
:description: Component library — layout, cards, forms, badges
Kida macros with CSS and themes. htmx-native, gorgeous by default.
:::{/card}

:::{card} Islands Contract
:icon: puzzle
:link: /chirp/docs/guides/islands/
:description: Framework-agnostic high-state mount roots
Mount isolated high-state widgets while keeping pages server-rendered.
:::{/card}

:::{card} No-Build High-State
:icon: lightning
:link: /chirp/docs/guides/no-build-high-state/
:description: State primitives without bundlers
Use islands + static ES modules for complex UI state while staying server-first.
:::{/card}

:::{card} Auth Hardening
:icon: shield
:link: /chirp/docs/guides/auth-hardening/
:description: Production checklist for auth and authz
Harden sessions, CSRF, abuse limits, security headers, and audit events.
:::{/card}

:::{card} Tools & MCP
:icon: wrench
:link: /chirp/docs/guides/tools/
:description: Register functions as MCP tools for AI agents
Humans use forms, agents use JSON-RPC. Same functions, two interfaces.
:::{/card}

:::{card} RenderPlan Middleware
:icon: eye
:link: /chirp/docs/guides/render-plan/
:description: Inspect rendering decisions from middleware
Read-only access to the frozen RenderPlan for analytics, caching, debugging.
:::{/card}

:::{/cards}
