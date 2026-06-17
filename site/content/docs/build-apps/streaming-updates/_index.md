---
title: Streaming and Updates
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

Stream HTML to the browser as it becomes ready, or push updates after the page
has loaded. This section covers the three return types that move content over
time: `Stream` and `Suspense` for the initial render, and `EventStream`
(Server-Sent Events) for post-load updates. Signals and the reactive system
build on `EventStream` to fan one server value out to many bound elements
automatically.

:::{note} Which one do I reach for?
A slow first paint that should appear section-by-section is `Stream`. A
dashboard whose shell should appear instantly while slow panels fill in is
`Suspense`. A feed that updates after the page is live is `EventStream`. For the
full picture, see [[docs/about/core-concepts/return-values|the return-type decision tree]].
:::

:::{cards}
:columns: 2
:gap: medium

:::{card} Streaming HTML & Suspense
:icon: monitor
:link: /chirp/docs/build-apps/streaming-updates/html-streaming/
:description: Progressive page rendering
Send the shell immediately, fill in content as data arrives. Suspense streams deferred blocks via OOB swaps.
:::{/card}

:::{card} Server-Sent Events
:icon: network
:link: /chirp/docs/build-apps/streaming-updates/server-sent-events/
:description: Real-time HTML updates
Push kida-rendered fragments to the browser over SSE.
:::{/card}

:::{card} Signals
:icon: network
:link: /chirp/docs/build-apps/streaming-updates/signals/
:description: Server-owned reactive values
Declare a live value once, bind it many places, update them all over one shared SSE connection.
:::{/card}

:::{card} Reactive System
:icon: refresh-cw
:link: /chirp/docs/build-apps/streaming-updates/reactive-system/
:description: Automatic SSE from data changes
Mutate your data; Chirp finds the affected blocks and pushes re-rendered fragments to connected browsers.
:::{/card}

:::{card} SSE Patterns
:icon: layers
:link: /chirp/docs/build-apps/streaming-updates/sse-patterns/
:description: Four update patterns
Display-only, client-managed, streaming append, and one-shot mutations.
:::{/card}

:::{/cards}
