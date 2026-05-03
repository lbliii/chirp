---
title: Understand Chirp
description: Learn the return-type model, app lifecycle, and configuration surface
draft: false
weight: 5
lang: en
type: doc
tags: [concepts, architecture, fundamentals, return-values]
keywords: [app, lifecycle, return values, configuration, concepts]
category: explanation
icon: book-open

cascade:
  type: doc
---

:::{cards}
:columns: 2
:gap: medium

Chirp's core model is type-driven: route handlers return values that carry
rendering intent, the app freezes before serving, and configuration is explicit.
Start here when you need the mental model behind the task-oriented sections.

:::{card} App Lifecycle
:icon: refresh-cw
:link: /chirp/docs/core-concepts/app-lifecycle/
:description: Mutable setup, frozen runtime
How Chirp's App transitions from configuration to serving.
:::{/card}

:::{card} Return Values
:icon: arrow-right
:link: /chirp/docs/core-concepts/return-values/
:description: The type is the intent
All the types route handlers can return and what they mean.
:::{/card}

:::{card} Configuration
:icon: settings
:link: /chirp/docs/core-concepts/configuration/
:description: AppConfig frozen dataclass
Every configuration option with IDE autocomplete.
:::{/card}

:::{/cards}
