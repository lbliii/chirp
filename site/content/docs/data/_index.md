---
title: Handle Forms and Data
description: Form parsing, validation, database access, query helpers, and migrations
draft: false
weight: 30
lang: en
type: doc
tags: [data, database, forms, validation, mutations]
keywords: [database, sqlite, postgresql, forms, multipart, validation]
category: guide
icon: database

cascade:
  type: doc
---

Use this section when request data becomes application data: parse forms,
validate mutations, query storage, paginate results, and keep optional data
extras explicit.

:::{cards}
:columns: 3
:gap: medium

:::{card} Database
:icon: database
:link: /chirp/docs/data/database/
:description: SQLite and PostgreSQL access
Typed async queries, row mapping, transactions, streaming, and LISTEN/NOTIFY.
:::{/card}

:::{card} Query Builder
:icon: search
:link: /chirp/docs/data/database/#query-builder
:description: Immutable chainable queries
Dynamic filters with `where_if()`, transparent SQL, typed results.
:::{/card}

:::{card} Migrations
:icon: upload
:link: /chirp/docs/data/database/#migrations
:description: Forward-only SQL migrations
Numbered SQL files, automatic tracking, runs at startup.
:::{/card}

:::{card} Forms & Validation
:icon: check-circle
:link: /chirp/docs/data/forms-validation/
:description: Form parsing and validation rules
Multipart forms, validation results, and error rendering.
:::{/card}

:::{/cards}
