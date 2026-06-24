---
title: Get Started
description: Install Chirp and build your first HTMX-friendly, server-rendered web application
draft: false
weight: 1
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

## Prerequisites

This documentation assumes you are comfortable with:

- **Python** (3.14+)
- **HTML** and basic HTTP (methods, forms, cookies)
- **htmx** basics — partial page updates via attributes like `hx-get` and `hx-target`
  ([htmx.org docs](https://htmx.org/docs/))

Helpful before you go deep:

- **Coming from Flask?** → [[docs/tutorials/coming-from-flask|Coming from Flask]]
- **Evaluating Chirp?** → [[docs/about/comparison|When to use Chirp]] and
  [[docs/about/non-goals|Non-goals]]
- **Agent or IDE tooling?** → site-wide doc index at `/chirp/llms.txt` (generated on build)

## Learning path

Follow [[docs/get-started/learning-path|the numbered learning path]] for the full
curriculum in order. The cards below are the same steps — start with the path page
if you want one checklist.

:::{cards}
:columns: 2
:gap: medium

:::{card} Learning Path
:icon: map
:link: /chirp/docs/get-started/learning-path/
:description: Numbered curriculum from install to deployment
The full first-week path in one page.
:::{/card}

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
