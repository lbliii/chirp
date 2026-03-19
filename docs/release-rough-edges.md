# Chirp Release — Rough Edges Deep Dive

Pre-release audit of failing examples and technical debt. Each section has root cause, fix, and effort estimate.

---

## 1. Page Shell Contract: Missing `page_root_inner`

**Error:** `Page template 'X' does not satisfy the registered page shell contract. Missing required block(s): page_root_inner.`

**Root cause:** ChirpUI's `CHIRPUI_PAGE_SHELL_CONTRACT` requires three blocks:

- `page_root` — target `#main` (sidebar + boosted nav)
- `page_root_inner` — target `#page-root` (tabbed page shell)
- `page_content` — target `#page-content-inner` (optional, triggers_shell_update=False)

Examples that use `use_chirp_ui(app)` must provide all required blocks. Several have `page_root` and `page_content` but omit `page_root_inner`.

**Fix pattern (from sortable_reorder):**

```html
{% block page_root %}
{% block page_root_inner %}
  ... page content ...
{% end %}
{% end %}
```

**Affected files:**


| Example        | Template                           | Current                 | Fix                                                                 |
| -------------- | ---------------------------------- | ----------------------- | ------------------------------------------------------------------- |
| contacts_shell | contacts/page.html                 | page_root, page_content | Add `{% block page_root_inner %}` wrapping content inside page_root |
| islands_shell  | page.html                          | page_root, page_content | Add page_root_inner                                                 |
| islands_shell  | about/page.html                    | page_root, page_content | Add page_root_inner                                                 |
| islands_shell  | dashboard/page.html                | page_root, page_content | Add page_root_inner                                                 |
| pages_shell    | projects/page.html                 | page_root, page_content | Add page_root_inner                                                 |
| pages_shell    | projects/{slug}/page.html          | **none**                | Add page_root, page_root_inner, page_content (wraps entire content) |
| pages_shell    | projects/{slug}/settings/page.html | page_root only          | Add page_root_inner, page_content                                   |


**Effort:** ~30 min. Wrap existing content in the missing block(s).

---

## 2. Dashboard Live: Kida Format Filter

**Error:** `ValueError: format filter uses str.format() with {} placeholders, not %. For numeric formatting use format_number (e.g. x | format_number(2))`

**Root cause:** Kida's `format` filter uses Python `str.format()` with `{}` placeholders. The `%`-style (`"%.2f"`) is not supported.

**Fix:** Replace `"%.2f" | format(x)` with either:

- `{{ "{:.2f}" | format(x) }}` — str.format style
- `{{ x | format_number(2) }}` — Kida numeric helper

**Affected lines in `examples/standalone/dashboard_live/templates/dashboard.html`:**

- Line 94: `${{ "%.2f" | format(stats.total_revenue) }}`
- Line 102: `${{ "%.2f" | format(stats.avg_order) }}`
- Line 134: `${{ "%.2f" | format(order.amount) }}`
- Line 155: `${{ "%.2f" | format(order.amount) }}` (in order_row block)

**Effort:** ~5 min. Search-replace 4 occurrences.

---

## 3. ChirpUI: hx-target="#update-result" Warning

**Error:** `hx-target="#update-result" — no element with id="update-result" found in any template.`

**Root cause:** `fragment_island_with_result` in chirp-ui creates a div with `mutation_result_id` (e.g. `"update-result"`) for forms that target it. The contract checker scans templates for hx-target attributes and warns when the target ID doesn't exist. The `#update-result` is referenced in component docs/examples but not all apps that use fragment_island provide it.

**Options:**

1. **Ignore** — It's a warning (▲), not an error. Apps that don't use `fragment_island_with_result` won't have this element; that's fine.
2. **ChirpUI** — If fragment_island.html or a shared layout defines a default `#update-result` placeholder, the warning goes away. Check if chirp-ui's fragment_island macro should add it.
3. **Contract checker** — Only warn for hx-target when the target is clearly app-specific (e.g. not from fragment_island_with_result pattern).

**Effort:** Low if we accept the warning; medium if we change the checker or chirp-ui.

---

## 4. Pages Shell: Context Provider Params

**Error:** `Route '/projects/{slug}' context provider param 'projects' is not a path param or provider type (may come from parent).`

**Root cause:** Nested routes inherit parent context. The checker flags `projects` and `project` as "not path param or provider" because they're provided by parent context providers, not by the route's own _context.py.

**Options:**

1. **Relax checker** — Allow params that exist in `cascade_ctx` from parent discovery.
2. **Add _context.py** — Each nested route could declare it receives `projects`/`project` from parent (redundant but satisfies checker).
3. **Document** — Add a note that this is expected for nested routes; treat as informational.

**Effort:** Medium if we change the checker; low if we document.

---

## 5. Exception Syntax: chirp_ui.py

**Location:** `src/chirp/ext/chirp_ui.py` line 98

**Current:** `except AttributeError, OSError:`

**Fix:** `except (AttributeError, OSError):`

Same pattern as shell_context.py and actions.py (already fixed). Python 3 requires the tuple form for multiple exceptions.

**Effort:** 1 min.

---

## 6. Route Meta Warnings (Informational)

**Error:** `Route '/X' has no _meta.py. Consider adding one for title, section, breadcrumb_label, etc.`

**Root cause:** Contract checker suggests _meta.py for SEO and shell context. Examples often omit it for brevity.

**Options:**

1. **Add _meta.py** to each example route dir — improves examples as reference.
2. **Downgrade to hint** — Make it a suggestion, not a warning.
3. **Leave as-is** — Warnings are informational; examples still work.

**Effort:** ~15 min to add minimal _meta.py to key examples.

---

## 7. Dashboard Template Not Referenced

**Warning:** `Template 'dashboard.html' is not referenced by any route or template.`

**Root cause:** The dashboard_live app may mount templates differently (e.g. via a custom route that doesn't go through standard page discovery). Need to verify how the route references the template.

**Effort:** Investigate dashboard_live app structure; likely a wiring issue.

---

## Summary: Release Checklist


| #   | Issue                                  | Effort | Priority                | Status |
| --- | -------------------------------------- | ------ | ----------------------- | ------ |
| 1   | Add page_root_inner to 7 templates     | 30 min | **P0** — Unblocks tests | ✅ Done |
| 2   | Fix dashboard format filter (4 places) | 5 min  | **P0** — Unblocks tests | ✅ Done |
| 5   | Fix chirp_ui.py except syntax          | 1 min  | **P0** — Bug            | ✅ Done |
| 3   | update-result warning                  | Low    | P2 — Cosmetic           | ✅ Done |
| 4   | Context provider params                | Medium | P2 — Refinement         | ✅ Done |
| 6   | _meta.py warnings                      | 15 min | P3 — Nice to have       | ✅ Done |
| 7   | dashboard.html reference               | TBD    | P2 — Investigate        | ✅ Done |


**All items complete.** All 405 example tests pass. Chirp check reports "All clear" for dashboard_live and pages_shell.