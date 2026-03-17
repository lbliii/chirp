# OOB Layout Chain

Dori-style layout chain: root layout wraps a page that extends an inner layout.
OOB regions (`{% region sidebar_oob %}`) are suppressed on full-page to avoid
orphaned fragments; they appear in fragment responses for HTMX swaps.

## Layout structure

- `_layout.html` — root layout with sidebar_oob region and content block
- `_page_layout.html` — extends _layout, adds page_root/page_content blocks
- `page.html` — extends _page_layout, provides page content

## Run

```bash
PYTHONPATH=src python examples/standalone/oob_layout_chain/app.py
```

Visit http://localhost:8000/
