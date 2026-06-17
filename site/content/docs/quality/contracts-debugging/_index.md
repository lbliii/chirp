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

Shipping a Chirp app to production, or staring at a swap that won't fire? This
section is the safety net. Chirp validates your hypermedia wiring — routes,
[[docs/build-apps/html-fragments/fragments|fragments]], OOB regions,
[[docs/build-apps/streaming-updates/server-sent-events|SSE]] payloads — at
startup, so broken UI fails loudly in CI instead of silently in front of users.
Start with **Debugging Swaps** if something is already broken; start with the
**Route Directory Contract** to see what `app.check()` enforces before you ship.

:::{cards}
:columns: 2
:gap: medium

:::{card} Debugging Swaps
:icon: shield
:link: /chirp/docs/quality/contracts-debugging/debugging-swaps/
:description: chirp check, DevTools, debug headers, and swap failure modes
Fix htmx, OOB, Suspense, SSE, and boosted navigation updates that won't fire.
:::{/card}

:::{card} Route Directory Contract
:icon: file-text
:link: /chirp/docs/quality/contracts-debugging/route-contract/
:description: Reserved files, route metadata, sections, and shell contracts
See exactly what fails CI before you ship filesystem routes and app shells.
:::{/card}

:::{card} Contract Category Reference
:icon: check-circle
:link: /chirp/docs/quality/contracts-debugging/categories/
:description: Categories, default severity, and fix targets
Look up any contract failure by name and dial its severity up or down.
:::{/card}

:::{card} OOB Registry
:icon: starburst
:link: /chirp/docs/quality/contracts-debugging/oob-registry/
:description: Fail-loud region validation
Catch empty OOB swaps that would silently wipe live DOM before users hit them.
:::{/card}

:::{/cards}
