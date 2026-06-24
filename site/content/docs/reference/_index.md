---
title: Reference
description: Complete API reference, errors, and configuration
draft: false
weight: 90
lang: en
type: doc
tags: [reference, api, errors]
keywords: [reference, api, errors, configuration, exports]
category: reference
icon: file-text

cascade:
  type: doc
---

Reach for this section when you need an exact answer — a function signature, an
error type, or a config field — not a tutorial. Each page is a lookup surface,
not a narrative: arrive via search, find the symbol, leave.

Site-wide machine-readable index: [`/chirp/llms.txt`](/chirp/llms.txt).

:::{cards}
:columns: 2
:gap: medium

:::{card} Glossary
:icon: book-open
:link: /chirp/docs/reference/glossary/
:description: Fragment, Page, OOB, Suspense, Signal, Shape, Contract, …
Hypermedia and Chirp terminology.
:::{/card}

:::{card} API Reference
:icon: code
:link: /chirp/docs/reference/api/
:description: Public API exports and signatures
Everything exported from `chirp.__init__`.
:::{/card}

:::{card} Errors
:icon: warning
:link: /chirp/docs/reference/errors/
:description: Error hierarchy and error handlers
Built-in exceptions and how to handle them.
:::{/card}

:::{card} CLI
:icon: terminal
:link: /chirp/docs/reference/cli/
:description: chirp new, chirp check, and shapes-codegen
The command-line entry point for scaffolding and validation.
:::{/card}

:::{/cards}
