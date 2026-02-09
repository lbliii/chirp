---
title: Data
description: Database access, form parsing, and validation
draft: false
weight: 70
lang: en
type: doc
tags: [data, database, forms, validation]
keywords: [database, sqlite, postgresql, forms, multipart, validation]
category: guide
icon: database

cascade:
  type: doc
---

:::{cards}
:columns: 3
:gap: medium

:::{card} Database
:icon: database
:link: ./database
:description: SQLite and PostgreSQL access
Typed async queries, row mapping, transactions, streaming, and LISTEN/NOTIFY.
:::{/card}

:::{card} Query Builder
:icon: search
:link: ./database#query-builder
:description: Immutable chainable queries
Dynamic filters with `where_if()`, transparent SQL, typed results.
:::{/card}

:::{card} Migrations
:icon: arrow-up-circle
:link: ./database#migrations
:description: Forward-only SQL migrations
Numbered SQL files, automatic tracking, runs at startup.
:::{/card}

:::{card} Forms & Validation
:icon: check-square
:link: ./forms-validation
:description: Form parsing and validation rules
Multipart forms, validation results, and error rendering.
:::{/card}

:::{/cards}
