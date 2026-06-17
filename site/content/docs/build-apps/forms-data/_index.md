---
title: Forms and Data
description: Form parsing, validation, database access, and verified SQL-to-render data contracts
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
validate mutations, query SQLite or Postgres, and define verified
SQL-to-render data contracts. Each topic below is its own page — start with
[[docs/build-apps/forms-data/forms-validation|Forms & Validation]] to handle a
POST, reach for the [[docs/build-apps/forms-data/database|Database]] when you
need storage, and define [[docs/build-apps/forms-data/shapes|Shapes]] when you
want `app.check()` to verify your SQL against your templates before you serve a
byte.

:::{child-cards}
:::
