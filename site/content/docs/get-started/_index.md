---
title: Get Started
description: Install Chirp and build your first HTMX-friendly, server-rendered web application
draft: false
weight: 2
lang: en
type: doc
tags: [getting-started, installation, quickstart]
keywords: [install, setup, quickstart, python web framework, htmx, server-rendered]
category: onboarding
icon: rocket

cascade:
  type: doc
---

New to Chirp? Start here. This section takes you from zero to a running,
server-rendered app that swaps HTML fragments over the wire — no SPA, no JSON
API. Coming from Flask or Django, you already know routes and templates; the new
idea is that the [[docs/about/core-concepts/return-values|return type is the intent]]
(return a `Fragment`, a `Page`, a stream), and Chirp handles content negotiation
and htmx awareness for you.

Read the cards below in order: install, build a hello-world in five minutes,
wire your first fragment loop, then learn the recommended project layout.

:::{cards}
:columns: 2
:gap: medium

:::{card} Installation
:icon: download
:link: /chirp/docs/get-started/installation/
:description: Install Chirp with pip, uv, or from source
Get Chirp running in your environment.
:::{/card}

:::{card} Quickstart
:icon: zap
:link: /chirp/docs/get-started/quickstart/
:description: Build your first Chirp app in 5 minutes
From hello world to fragment rendering.
:::{/card}

:::{card} First Fragment App
:icon: layers
:link: /chirp/docs/get-started/first-fragment-app/
:description: Build a small htmx app with one template
Routes, `Page`, `Fragment`, a form POST, and `chirp check`.
:::{/card}

:::{card} Project Layout
:icon: folder
:link: /chirp/docs/get-started/project-layout/
:description: Recommended directory structure
Conventions used by chirp new.
:::{/card}

:::{/cards}
