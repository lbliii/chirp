---
title: Contracts and Debugging
description: Contract checks, route-directory validation, DevTools, debug headers, and swap troubleshooting
draft: false
weight: 10
lang: en
type: doc
tags: [contracts, debugging, htmx, devtools]
keywords: [contracts, app check, chirp check, devtools, debugging, route contract]
category: guide
icon: shield

cascade:
  type: doc
---

Use this section when Chirp needs to prove the server-rendered UI is wired
correctly before users see it: route contracts, htmx targets, OOB regions,
Suspense blocks, SSE payloads, and debug tooling.

:::{cards}
:columns: 2
:gap: medium

:::{card} Debugging Swaps
:icon: shield
:link: /chirp/docs/quality/contracts-debugging/debugging-swaps/
:description: chirp check, DevTools, debug headers, and swap failure modes
Diagnose broken htmx, OOB, Suspense, SSE, and boosted navigation updates.
:::{/card}

:::{card} Route Directory Contract
:icon: file-text
:link: /chirp/docs/quality/contracts-debugging/route-contract/
:description: Reserved files, route metadata, sections, and shell contracts
Understand what `app.check()` validates for filesystem routes and app shells.
:::{/card}

:::{card} Contract Category Reference
:icon: list-checks
:link: /chirp/docs/quality/contracts-debugging/categories/
:description: Categories, default severity, and fix targets
Tune `chirp check` policy with source-backed category names.
:::{/card}

:::{card} OOB Registry
:icon: target
:link: /chirp/docs/quality/contracts-debugging/oob-registry/
:description: Fail-loud region validation
Register shell regions and catch missing OOB blocks before users see empty swaps.
:::{/card}

:::{/cards}
