---
title: Middleware
description: Protocol-based middleware system
draft: false
weight: 50
lang: en
type: doc
tags: [middleware, pipeline, protocol]
keywords: [middleware, cors, static, sessions, auth, csrf, protocol]
category: guide
icon: sliders

cascade:
  type: doc
---

:::{cards}
:columns: 2
:gap: medium

:::{card} Overview
:icon: layers
:link: ./overview
:description: Protocol definition and pipeline execution
How middleware works -- no base class, no inheritance.
:::{/card}

:::{card} Built-in Middleware
:icon: package
:link: ./builtin
:description: CORS, StaticFiles, Sessions, Auth, CSRF
Middleware that ships with Chirp.
:::{/card}

:::{card} Custom Middleware
:icon: code
:link: ./custom
:description: Writing your own middleware
Functions, classes, and real-world patterns.
:::{/card}

:::{/cards}
