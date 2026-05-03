---
title: Validate Contracts and Debug UI
description: Contract checks, route-directory validation, DevTools, debug headers, and swap troubleshooting
draft: false
weight: 45
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
:link: /chirp/docs/contracts/debugging-swaps/
:description: chirp check, DevTools, debug headers, and swap failure modes
Diagnose broken htmx, OOB, Suspense, SSE, and boosted navigation updates.
:::{/card}

:::{card} Route Directory Contract
:icon: file-text
:link: /chirp/docs/contracts/route-contract/
:description: Reserved files, route metadata, sections, and shell contracts
Understand what `app.check()` validates for filesystem routes and app shells.
:::{/card}

:::{/cards}
