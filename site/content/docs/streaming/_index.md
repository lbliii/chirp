---
title: Stream and Push Updates
description: Streaming HTML, Suspense, Server-Sent Events, and reactive updates
draft: false
weight: 40
lang: en
type: doc
tags: [streaming, suspense, sse, real-time]
keywords: [streaming, html, sse, server-sent-events, real-time, chunked]
category: guide
icon: zap

cascade:
  type: doc
---

Use this section when content should arrive over time: initial page rendering
with `Stream` or `Suspense`, or post-load updates with `EventStream`.

:::{cards}
:columns: 2
:gap: medium

:::{card} Streaming HTML & Suspense
:icon: monitor
:link: /chirp/docs/streaming/html-streaming/
:description: Progressive page rendering
Send the shell immediately, fill in content as data arrives. Suspense streams deferred blocks via OOB swaps.
:::{/card}

:::{card} Server-Sent Events
:icon: network
:link: /chirp/docs/streaming/server-sent-events/
:description: Real-time HTML updates
Push kida-rendered fragments to the browser over SSE.
:::{/card}

:::{card} Reactive System
:icon: refresh-cw
:link: /chirp/docs/streaming/reactive-system/
:description: Automatic SSE from data changes
ReactiveBus, DependencyIndex, derived paths, and observability counters.
:::{/card}

:::{card} SSE Patterns
:icon: layers
:link: /chirp/docs/streaming/sse-patterns/
:description: Four update patterns
Display-only, client-managed, streaming append, and one-shot mutations.
:::{/card}

:::{/cards}
