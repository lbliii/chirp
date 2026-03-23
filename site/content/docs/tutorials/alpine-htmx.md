---
title: Alpine + htmx
description: Combine Alpine.js for local state with htmx for server round-trips
draft: false
weight: 25
lang: en
type: doc
tags: [tutorial, alpine, htmx, dropdown, modal]
keywords: [alpine, htmx, dropdown, modal, local-state]
category: tutorial
---

## Overview

This tutorial shows how to use Alpine.js and htmx together: Alpine for dropdowns and modals, htmx for form submission and partial updates.

## Setup

If you use `chirp-ui`, Alpine is enabled automatically by `use_chirp_ui(app)`. Otherwise, enable it in your config:

```python
config = AppConfig(alpine=True)
app = App(config=config)
```

Chirp auto-injects both htmx and Alpine into full-page HTML responses. For named components that must survive htmx boosted navigation, use `Alpine.safeData()` instead of `Alpine.data()` (see the [Alpine guide](../guides/alpine.md#registering-custom-components-alpinesafedata)).

## Dropdown with htmx Form

A filter dropdown that submits via htmx when an option is selected:

```html
{% from "chirp/alpine.html" import dropdown %}

{% call dropdown("Filter by status") %}
  <form hx-get="/tasks" hx-target="#task-list" hx-swap="innerHTML">
    <input type="hidden" name="status" value="open">
    <button type="submit" @click="open = false">Open</button>
  </form>
  <form hx-get="/tasks" hx-target="#task-list" hx-swap="innerHTML">
    <input type="hidden" name="status" value="closed">
    <button type="submit" @click="open = false">Closed</button>
  </form>
{% end %}

<div id="task-list">
  {% for task in tasks %}
    <div class="task">{{ task.title }}</div>
  {% endfor %}
</div>
```

Alpine controls the dropdown open/close state. htmx handles the filter request and swap.

## Modal with htmx Form

A "New task" button that opens a modal; the form submits via htmx and closes the modal on success. Use `managed=false` so the parent's `open` state controls the modal:

```html
{% from "chirp/alpine.html" import modal %}

<div x-data="{ open: false }">
  <button type="button" @click="open = true">New Task</button>
  {% call modal("new-task-modal", title="New Task", managed=false) %}
    <form hx-post="/tasks" hx-target="#task-list" hx-swap="beforeend"
          @htmx:after-request="open = false">
      <input name="title" required>
      <button type="submit">Create</button>
    </form>
  {% end %}
</div>

<div id="task-list">
  {% for task in tasks %}
    <div class="task">{{ task.title }}</div>
  {% endfor %}
</div>
```

The parent `x-data` holds `open`. The button sets `open = true`; the form's `@htmx:after-request` sets `open = false` after a successful submit.

## x-cloak for Modals

Add this to your CSS so modals stay hidden until Alpine initializes:

```css
[x-cloak] { display: none !important; }
```
