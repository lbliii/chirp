---
title: Examples
description: Full-featured Chirp applications showcasing the framework
draft: false
weight: 105
lang: en
type: doc
tags: [examples, demos, rag, sse, streaming]
keywords: [examples, demos, rag, sse, streaming, fragments]
category: tutorial
icon: box

cascade:
  type: doc
---

:::{cards}
:columns: 2
:gap: medium

:::{card} RAG Demo
:icon: message-circle
:link: ./rag-demo
:description: Streaming AI Q&A with cited sources, dual-model comparison, and zero client JS
The flagship Chirp example: fragments, SSE, event delegation, and free-threading.
:::{/card}

:::{card} Contacts Shell
:icon: users
:link: https://github.com/lbliii/chirp/tree/main/examples/chirpui/contacts_shell
:description: CRUD contacts with chirp-ui app shell, sidebar navigation, and full test coverage
Full CRUD app with app shell, boosted navigation, and fragment swaps.
:::{/card}

:::{card} Kanban Shell
:icon: layout
:link: https://github.com/lbliii/chirp/tree/main/examples/chirpui/kanban_shell
:description: Drag-and-drop Kanban board with OOB swaps, SSE, and toast notifications
Real-time board with multi-fragment updates and SSE live sync.
:::{/card}

:::{/cards}
