---
title: Guides
description: Best practices and patterns for building accessible, secure apps
draft: false
weight: 105
lang: en
type: doc
tags: [guides, best-practices, accessibility]
keywords: [guides, accessibility, wcag, best-practices]
category: guide
icon: book

cascade:
  type: doc
---

:::{cards}
:columns: 2
:gap: medium

:::{card} Accessibility
:icon: accessibility
:link: ./accessibility
:description: Semantic markup, ARIA, and WCAG alignment
Build inclusive apps with Chirp.
:::{/card}

:::{card} Alpine.js
:icon: layers
:link: ./alpine
:description: Local UI state — dropdowns, modals, tabs
Complement htmx with Alpine for client-only interactivity.
:::{/card}

:::{card} Islands Contract
:icon: puzzle
:link: ./islands
:description: Framework-agnostic high-state mount roots
Mount isolated high-state widgets while keeping pages server-rendered.
:::{/card}

:::{card} No-Build High-State
:icon: bolt
:link: ./no-build-high-state
:description: State primitives without bundlers
Use islands + static ES modules for complex UI state while staying server-first.
:::{/card}

:::{card} Auth Hardening
:icon: shield
:link: ./auth-hardening
:description: Production checklist for auth and authz
Harden sessions, CSRF, abuse limits, security headers, and audit events.
:::{/card}

:::{/cards}
