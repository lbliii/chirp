# Sortable List Reorder

Alpine + HTMX drag-and-drop without Sortable.js. Demonstrates native HTML5
drag-and-drop with chirp-ui `sortable_list`, Alpine.js for visual feedback
(`dataset.draggingIdx`, `overCount`), and HTMX form submission for reorder.

## Run

```bash
pip install chirp[ui]
cd examples/sortable_reorder && python app.py
```

## What it demonstrates

- **chirp-ui sortable_list** — CSS-styled drag affordances
- **Alpine 3** — `dataset.draggingIdx` on the list (no `$parent`), per-item
  `overCount` for drop indicator (avoids flicker over child elements)
- **Hidden form + HTMX** — On drop: set `from_idx`/`to_idx`, call
  `htmx.trigger(form, 'submit')`; server returns fragment, `hx-select="#item-list"`
  swaps the list
- **No Sortable.js** — Pure Alpine + HTMX, zero extra dependencies

## Pattern

See [chirp-ui DND-FRAGMENT-ISLAND.md](https://github.com/b-stack/chirp-ui/blob/main/docs/DND-FRAGMENT-ISLAND.md)
and Chirp's [htmx-patterns.md](../site/content/docs/tutorials/htmx-patterns.md)
for the full pattern.
