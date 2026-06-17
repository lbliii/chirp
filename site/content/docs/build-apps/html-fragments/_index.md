---
title: HTML Fragments
description: Templates, named blocks, Page, Fragment, OOB swaps, and kida integration
draft: false
weight: 20
lang: en
type: doc
tags: [templates, kida, rendering, fragments, oob]
keywords: [templates, kida, rendering, fragments, page, oob, filters]
category: guide
icon: layers

cascade:
  type: doc
---

HTML over the wire: one template, many modes. Chirp renders a single template
with named blocks as a full page, an htmx fragment, a multi-target
[[docs/build-apps/html-fragments/fragments|OOB swap]], or a streamed
[[docs/build-apps/streaming-updates/_index|Suspense or SSE payload]] — the
return type decides which. A *fragment* is one of those named blocks rendered on
its own; an *OOB swap* updates several regions of the page from a single
response. This section is for the hypermedia practitioner who wants those
return-type mechanics in detail.

:::{note} Where to start
New to Chirp templates? Begin with **Rendering**. Already build with htmx and
just want the return-type mapping? Jump straight to **Fragments**.
:::

:::{child-cards}
:::
