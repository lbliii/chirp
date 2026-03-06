# Proposal: Kanban Shell Example

**Status**: Proposal  
**Created**: 2025-03-06

---

## Summary

Create a new, separate Chirp example `kanban_shell/` that reimplements the kanban board using the **app shell pattern**, **chirp-ui** components, and **mount_pages** routing. It showcases the full stack of chirp, kida, and chirp-ui improvements while preserving the kanban example's core features (auth, CRUD, OOB swaps, SSE, filtering).

---

## Current Kanban Analysis

### Architecture (`examples/kanban/`)

| Aspect | Current Implementation |
|--------|------------------------|
| **Layout** | Custom `app-layout` div structure (header, sidebar, main-content) |
| **Routing** | `@app.route()` for all endpoints: `/`, `/login`, `/tasks`, `/filter`, `/events` |
| **Auth** | SessionMiddleware + AuthMiddleware + CSRFMiddleware |
| **Templates** | Standalone `board.html` with custom components in `components/` |
| **Styling** | Custom `board.css` + inline styles |
| **Components** | `_card.html`, `_column.html`, `_field.html`, `_badge.html` (Kida macros) |

### Features Demonstrated

- **Chirp**: OOB multi-fragment swaps, EventStream (SSE), Fragment/Page, ValidationError, form_or_errors, login_required, current_user()
- **Kida**: `{% imports %}`, `{% fragment %}`, `{% match %}`, `{% let %}`, `{% unless %}`, `{% cache %}`, `?.`, `??`, `| selectattr`, `| map`, `| compact`, `| unique`, `| sort`
- **htmx**: hx-swap-oob, hx-sync, hx-boost, hx-ext="sse", HX-Trigger

### Gaps vs. New Stack

1. **No app shell** — custom layout, not chirpui-app-shell
2. **No chirp-ui** — custom card/column/badge instead of chirpui components
3. **No mount_pages** — imperative routing only
4. **No shell actions** — header has no ShellActions bar
5. **Custom toast** — manual div + JS, not chirpui toast
6. **No filter_bar** — sidebar uses raw checkboxes
7. **No dnd primitives** — chirp-ui has `dnd_board`, `dnd_column`, `dnd_card` (visual structure; Alpine/HTMX wiring left to consumer)

---

## Proposed: `kanban_shell/` Example

### Directory Structure

```text
examples/kanban_shell/
  app.py                    # App setup, middleware, API routes
  README.md
  test_app.py
  pages/
    _layout.html            # chirpui-app-shell (topbar, sidebar, main)
    _context.py             # Root context (users, columns, shell_actions)
    login/
      page.py               # GET /login
      page.html
    board/
      page.py               # GET / (board index)
      page.html             # Board content
      _context.py           # Board context (tasks, filters)
  api/                      # API routes (or inline in app.py)
    # Tasks CRUD, move, filter, events — see "Routing Strategy"
  components/               # Kanban-specific components (task_card, etc.)
    _task_card.html
    _column.html
  static/
    board.css               # Kanban-specific overrides (minimal)
```

### App Shell Pattern

**`pages/_layout.html`** — Extends chirpui shell or mirrors pages_shell:

- `chirpui-app-shell` with topbar, sidebar, main
- `hx-boost="true"` on main, `hx-target="#main"`, `hx-select="#page-content"`
- Sidebar: Board link, Filters (priority, assignee, tag) — uses `filter_bar` or `action_strip`
- Topbar: Brand "Kanban", shell_actions (New task, overflow), user avatar + logout
- `toast_container()` for delete/undo notifications

**`pages/_context.py`** — Root context:

- `columns` (COLUMNS)
- `shell_actions` — ShellActions with primary ("New task") and overflow
- `current_user` — from get_user() if authenticated

### Chirp-UI Components to Use

| Component | Use Case |
|-----------|----------|
| `chirpui/card.html` | Task cards via `card` or `card_main_link`; column headers |
| `chirpui/badge.html` | Priority badge, tag badges |
| `chirpui/button.html` | Move buttons, delete, add task |
| `chirpui/layout.html` | `container`, `stack`, `grid`, `page_header` for board layout |
| `chirpui/filter_bar.html` | Filter sidebar (priority, assignee, tag checkboxes) |
| `chirpui/forms.html` | `text_field`, `select_field` for add/edit forms |
| `chirpui/toast.html` | `toast_container()` + OOB toast on delete |
| `chirpui/inline_edit_field.html` | Optional: task title edit-in-place |
| `chirpui/dnd.html` | `dnd_board`, `dnd_column`, `dnd_card` for kanban structure (visual only; move still via htmx POST) |

### Kida Features to Showcase

- `{% imports %}` — component imports
- `{% fragment %}` — OOB-only blocks for column/card/stats swaps
- `{% match %}` — move buttons by status
- `{% let %}` — assignees, tags, stats
- `{% unless %}` — empty states
- `?.`, `??` — optional chaining, null coalescing
- `| selectattr`, `| map`, `| compact`, `| unique`, `| sort` — filter/sort in templates
- `{% cache %}` — stats fragment (if still useful)
- **Future**: List comprehensions (RFC in progress) for `[{"value": s, "label": s | capitalize} for s in options]`

### Routing Strategy

Per [filesystem-routing.md](site/content/docs/routing/filesystem-routing.md): *"You can mix both: `app.mount_pages()` for the main app shell, and `@app.route()` for API endpoints."*

- **mount_pages**: `/` (board), `/login` — page.py handlers
- **@app.route** (in app.py): `/tasks` (POST), `/tasks/{id}` (PUT, DELETE), `/tasks/{id}/edit`, `/tasks/{id}/move/{status}`, `/filter`, `/events`, `/login` (POST), `/logout` (POST)

Auth routes (`/login` GET/POST, `/logout`) can stay as `@app.route` since they're not page content; or `/login` can be a mounted page with a `post` handler.

**Recommended**: Keep `/login` as a mounted page (`pages/login/page.py` with `get` and `post`). All task API routes as `@app.route` before `mount_pages`.

### Key Implementation Details

1. **app.py**
   - `use_chirp_ui(app)` for chirpui CSS and filters
   - Session, Auth, CSRF middleware (same as kanban)
   - StaticFiles for `static/` (board.css)
   - `@app.route` for task CRUD, move, filter, events, logout
   - `app.mount_pages("pages")` after routes

2. **Board page**
   - `Page("board/page.html", "page_content", page_block_name="page_root", ...)` for list-style page
   - Context from `_context.py` cascade: columns, board, active_filters, shell_actions

3. **OOB + SSE**
   - Same pattern as kanban: column fragments, stats fragment, task card fragment
   - SSE at `/events` pushes OOB fragments on simulated moves
   - HX-Trigger `taskDeleted` → toast via chirpui toast OOB or `toast()` in response

4. **Toast**
   - Replace custom toast div with `toast_container()` in layout
   - On delete: return `OOB(..., toast("Task deleted.", variant="info"))` or use HX-Trigger + client-side toast

5. **Filter sidebar**
   - Use `filter_bar` with `hx-get="/filter"` and `hx-include`
   - Or `action_strip` with checkbox controls

---

## Comparison: kanban vs kanban_shell

| Aspect | kanban | kanban_shell |
|-------|--------|--------------|
| Layout | Custom app-layout | chirpui-app-shell |
| Routing | All @app.route | mount_pages + @app.route |
| Components | Custom _card, _column | chirpui card, badge, dnd_* |
| Filters | Raw checkboxes | filter_bar / action_strip |
| Toast | Custom div + JS | chirpui toast_container + toast() |
| Shell actions | None | ShellActions (New task, overflow) |
| Forms | Custom _field | chirpui forms (text_field, select_field) |
| Styling | board.css | chirpui.css + board.css overrides |
| Page structure | Single board.html | pages/board/page.html + _layout |

---

## Migration Path

1. **Phase 1**: Create `kanban_shell/` with app.py, pages/_layout.html, pages/_context.py, login page.
2. **Phase 2**: Add board page with chirpui card, badge, layout. Wire OOB fragments.
3. **Phase 3**: Add API routes (tasks CRUD, move, filter, events). Reuse storage/validation from kanban.
4. **Phase 4**: Add filter_bar, toast, shell actions. Optional: inline_edit_field for task title.
5. **Phase 5**: Tests (mirror kanban test_app.py structure).

---

## Open Questions

1. **dnd_board vs custom columns**: chirp-ui `dnd_board`/`dnd_column`/`dnd_card` provide structure but no drag-drop behavior (Alpine/HTMX left to consumer). Current kanban uses htmx POST for moves. Use dnd_* for visual consistency with chirp-ui, or keep custom column structure for clarity?
2. **Login page placement**: Mounted at `pages/login/` or keep as `@app.route("/login")`? Mounted is more consistent with app shell.
3. **Suspense**: Add deferred stats block (e.g. "High priority count" loaded async) to showcase Suspense in a kanban context?

---

## References

- `examples/kanban/` — current implementation
- `examples/pages_shell/` — app shell pattern, mount_pages, _context cascade
- `examples/contacts/` — htmx CRUD, ValidationError, OOB
- chirp-ui: `dnd.html`, `card.html`, `badge.html`, `filter_bar.html`, `toast.html`, `forms.html`
- chirp: `site/content/docs/routing/filesystem-routing.md`
- kida: `plan/rfc-list-comprehensions.md` (future)
