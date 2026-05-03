---
title: UI and Extensions
description: Shells, accessibility, Alpine, ChirpUI, islands, tools, and extension patterns
draft: false
weight: 50
lang: en
type: doc
tags: [guides, best-practices, accessibility, shells, extensions]
keywords: [guides, htmx, server-rendered, accessibility, shells, extensions]
category: guide
icon: book

cascade:
  type: doc
---

Use this section for UI surfaces that sit around or beyond a single route:
shells, accessibility, client-owned islands, ChirpUI, and tool registration.

:::{cards}
:columns: 2
:gap: medium

:::{card} Accessibility
:icon: user
:link: /chirp/docs/build-apps/ui-extensions/accessibility/
:description: Semantic markup, ARIA, and WCAG alignment
Build inclusive apps with Chirp.
:::{/card}

:::{card} Alpine.js
:icon: layers
:link: /chirp/docs/build-apps/ui-extensions/alpine/
:description: Local UI state — dropdowns, modals, tabs
Complement htmx with Alpine for client-only interactivity.
:::{/card}

:::{card} Shells
:icon: sidebar
:link: /chirp/docs/build-apps/ui-extensions/shells/
:description: The three root layouts — boost, shell, app-shell
Pick exactly one per app. Includes the decision table, the `hx-select` distinction, and what is *not* a shell.
:::{/card}

:::{card} App Shells
:icon: sidebar
:link: /chirp/docs/build-apps/ui-extensions/app-shell/
:description: chirp-ui's app_shell_layout — sidebar, topbar, OOB regions
The opinionated shell with persistent chrome. One of three shells; see [Shells](/chirp/docs/build-apps/ui-extensions/shells/) for the others.
:::{/card}

:::{card} Boosted Navigation
:icon: arrow-right
:link: /chirp/docs/build-apps/ui-extensions/boosted-navigation/
:description: hx-boost contract, cross-shell redirects, debug warnings
How swaps work, when they redirect, and the tripwires that catch silent failures.
:::{/card}

:::{card} UI layers & shell regions
:icon: layers
:link: /chirp/docs/build-apps/ui-extensions/ui-layers/
:description: Glossary — app shell, page chrome, surface chrome, OOB ids
One vocabulary for Chirp + chirp-ui layouts and ``chirp.shell_regions``.
:::{/card}

:::{card} chirp-ui
:icon: palette
:link: /chirp/docs/build-apps/ui-extensions/chirp-ui/
:description: Component library — layout, cards, forms, badges
Kida macros with CSS and themes. htmx-native, gorgeous by default.
:::{/card}

:::{card} Islands Contract
:icon: puzzle
:link: /chirp/docs/build-apps/ui-extensions/islands/
:description: Framework-agnostic high-state mount roots
Mount isolated high-state widgets while keeping pages server-rendered.
:::{/card}

:::{card} No-Build High-State
:icon: lightning
:link: /chirp/docs/build-apps/ui-extensions/no-build-high-state/
:description: State primitives without bundlers
Use islands + static ES modules for complex UI state while staying server-first.
:::{/card}

:::{card} Tools & MCP
:icon: wrench
:link: /chirp/docs/build-apps/ui-extensions/tools/
:description: Register functions as MCP tools for AI agents
Humans use forms, agents use JSON-RPC. Same functions, two interfaces.
:::{/card}

:::{/cards}
