---
title: Core Concepts
description: Understand the fundamental building blocks of Chirp
draft: false
weight: 20
lang: en
type: doc
tags: [concepts, architecture, fundamentals]
keywords: [app, lifecycle, return values, configuration, concepts]
category: explanation
icon: book-open

cascade:
  type: doc
---

:::{cards}
:columns: 2
:gap: medium

:::{card} App Lifecycle
:icon: refresh-cw
:link: ./app-lifecycle
:description: Mutable setup, frozen runtime
How Chirp's App transitions from configuration to serving.
:::{/card}

:::{card} Return Values
:icon: corner-down-right
:link: ./return-values
:description: The type is the intent
All the types route handlers can return and what they mean.
:::{/card}

:::{card} Configuration
:icon: settings
:link: ./configuration
:description: AppConfig frozen dataclass
Every configuration option with IDE autocomplete.
:::{/card}

:::{/cards}
